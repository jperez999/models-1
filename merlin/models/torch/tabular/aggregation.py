#
# Copyright (c) 2021, NVIDIA CORPORATION.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import torch

from merlin.schema import Schema, Tags

from ...config.schema import requires_schema
from ..typing import TabularData
from ..utils.torch_utils import calculate_batch_size_from_input_size
from .base import TabularAggregation, tabular_aggregation_registry


@tabular_aggregation_registry.register("concat")
class ConcatFeatures(TabularAggregation):
    """Aggregation by stacking all values in TabularData, all non-sequential values will be
    converted to a sequence.

    The output of this concatenation will have 3 dimensions.
    """

    def forward(
        self,
        inputs: TabularData,
    ) -> torch.Tensor:
        self._expand_non_sequential_features(inputs)
        self._check_concat_shapes(inputs)

        tensors = []
        for name in sorted(inputs.keys()):
            val = inputs[name]
            tensors.append(val)

        return torch.cat(tensors, dim=-1)

    def forward_output_size(self, input_size):
        agg_dim = sum([i[-1] for i in input_size.values()])
        output_size = self._get_agg_output_size(input_size, agg_dim)
        return output_size


@tabular_aggregation_registry.register("stack")
class StackFeatures(TabularAggregation):
    """Aggregation by stacking all values in input dictionary in the given dimension.

    Parameters
    ----------
    axis: int, default=-1
        Axis to use for the stacking operation.
    """

    def __init__(self, axis: int = -1):
        super().__init__()
        self.axis = axis

    def forward(self, inputs: TabularData) -> torch.Tensor:
        self._expand_non_sequential_features(inputs)
        self._check_concat_shapes(inputs)

        tensors = []
        for name in sorted(inputs.keys()):
            tensors.append(inputs[name])

        return torch.stack(tensors, dim=self.axis)

    def forward_output_size(self, input_size):
        batch_size = calculate_batch_size_from_input_size(input_size)
        last_dim = list(input_size.values())[0][-1]

        return batch_size, len(input_size), last_dim


class ElementwiseFeatureAggregation(TabularAggregation):
    def _check_input_shapes_equal(self, inputs):
        all_input_shapes_equal = len(set([x.shape for x in inputs.values()])) == 1
        if not all_input_shapes_equal:
            raise ValueError(
                "The shapes of all input features are not equal, which is required for element-wise"
                " aggregation: {}".format({k: v.shape for k, v in inputs.items()})
            )


@tabular_aggregation_registry.register("element-wise-sum")
class ElementwiseSum(ElementwiseFeatureAggregation):
    """Aggregation by first stacking all values in TabularData in the first dimension, and then
    summing the result."""

    def __init__(self):
        super().__init__()
        self.stack = StackFeatures(axis=0)

    def forward(self, inputs: TabularData) -> torch.Tensor:
        self._expand_non_sequential_features(inputs)
        self._check_input_shapes_equal(inputs)
        return self.stack(inputs).sum(dim=0)

    def forward_output_size(self, input_size):
        batch_size = calculate_batch_size_from_input_size(input_size)
        last_dim = list(input_size.values())[0][-1]

        return batch_size, last_dim


@tabular_aggregation_registry.register("element-wise-sum-item-multi")
@requires_schema
class ElementwiseSumItemMulti(ElementwiseFeatureAggregation):
    """Aggregation by applying the `ElementwiseSum` aggregation to all features except the item-id,
    and then multiplying this with the item-ids.

    Parameters
    ----------
    schema: DatasetSchema
    """

    def __init__(self, schema: Schema = None):
        super().__init__()
        self.stack = StackFeatures(axis=0)
        self.schema = schema
        self.item_id_col_name = None

    def forward(self, inputs: TabularData) -> torch.Tensor:
        item_id_inputs = self.get_item_ids_from_inputs(inputs)

        self._expand_non_sequential_features(inputs)
        self._check_input_shapes_equal(inputs)

        item_id_column = self.schema.select_by_tag(Tags.ITEM_ID).first.name
        other_inputs = {k: v for k, v in inputs.items() if k != item_id_column}
        other_inputs_sum = self.stack(other_inputs).sum(dim=0)
        result = item_id_inputs.multiply(other_inputs_sum)
        return result

    def forward_output_size(self, input_size):
        batch_size = calculate_batch_size_from_input_size(input_size)
        last_dim = list(input_size.values())[0][-1]

        return batch_size, last_dim
