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

import pytest
import torch

import merlin.models.torch as ml
from merlin.models.utils.schema import create_categorical_column
from merlin.schema import Schema, Tags


@pytest.mark.parametrize("replacement_prob", [0.1, 0.3, 0.5, 0.7])
def test_stochastic_swap_noise(replacement_prob):
    NUM_SEQS = 100
    SEQ_LENGTH = 80
    PAD_TOKEN = 0

    # Creating some input sequences with padding in the end
    # (to emulate sessions with different lengths)
    seq_inputs = {
        "categ_seq_feat": torch.tril(
            torch.randint(low=1, high=100, size=(NUM_SEQS, SEQ_LENGTH)), 1
        ),
        "cont_seq_feat": torch.tril(torch.rand((NUM_SEQS, SEQ_LENGTH)), 1),
        "categ_non_seq_feat": torch.randint(low=1, high=100, size=(NUM_SEQS,)),
    }

    ssn = ml.StochasticSwapNoise(pad_token=PAD_TOKEN, replacement_prob=replacement_prob)
    out_features_ssn = ssn(seq_inputs, input_mask=seq_inputs["categ_seq_feat"] != PAD_TOKEN)

    for fname in seq_inputs:
        replaced_mask = out_features_ssn[fname] != seq_inputs[fname]
        replaced_mask_non_padded = torch.masked_select(
            replaced_mask, seq_inputs[fname] != PAD_TOKEN
        )
        replacement_rate = replaced_mask_non_padded.float().mean()
        assert replacement_rate == pytest.approx(replacement_prob, abs=0.15)


# @pytest.mark.parametrize("replacement_prob", [0.1, 0.3, 0.5, 0.7])
# def test_stochastic_swap_noise_with_tabular_features(
#     yoochoose_schema, torch_yoochoose_like, replacement_prob
# ):
#     PAD_TOKEN = 0
#
#     inputs = torch_yoochoose_like
#     tab_module = ml.TabularSequenceFeatures.from_schema(yoochoose_schema)
#     out_features = tab_module(inputs)
#
#     ssn = ml.StochasticSwapNoise(
#         pad_token=PAD_TOKEN, replacement_prob=replacement_prob, schema=yoochoose_schema
#     )
#     out_features_ssn = tab_module(inputs, pre=ssn)
#
#     for fname in out_features:
#         replaced_mask = out_features_ssn[fname] != out_features[fname]
#
#         # Ignoring padding items to compute the mean replacement rate
#         feat_non_padding_mask = inputs[fname] != PAD_TOKEN
#         # For embedding features it is necessary to expand the mask
#         if len(replaced_mask.shape) > len(feat_non_padding_mask.shape):
#             feat_non_padding_mask = feat_non_padding_mask.unsqueeze(-1)
#         replaced_mask_non_padded = torch.masked_select(replaced_mask, feat_non_padding_mask)
#         replacement_rate = replaced_mask_non_padded.float().mean()
#         assert replacement_rate == pytest.approx(replacement_prob, abs=0.15)


@pytest.mark.parametrize("layer_norm", ["layer-norm", ml.TabularLayerNorm()])
def test_layer_norm(tabular_schema, torch_tabular_data, layer_norm):
    schema = tabular_schema.select_by_tag(Tags.CATEGORICAL)

    emb_module = ml.EmbeddingFeatures.from_schema(
        schema, embedding_dims={"item_id": 100}, embedding_dim_default=64, post=layer_norm
    )

    out = emb_module(torch_tabular_data)

    assert list(out["item_id"].shape) == [100, 100]
    assert list(out["categories"].shape) == [100, 64]


def test_stochastic_swap_noise_raise_exception_not_2d_item_id():

    s = Schema(
        [
            create_categorical_column("item_id_feat", num_items=1000, tags=[Tags.ITEM_ID.value]),
        ]
    )

    NUM_SEQS = 100
    SEQ_LENGTH = 80
    PAD_TOKEN = 0

    seq_inputs = {
        "item_id_feat": torch.tril(
            torch.randint(low=1, high=100, size=(NUM_SEQS, SEQ_LENGTH, 64)), 1
        ),
    }

    ssn = ml.StochasticSwapNoise(pad_token=PAD_TOKEN, replacement_prob=0.3, schema=s)

    with pytest.raises(ValueError) as excinfo:
        ssn(seq_inputs)
    assert "To extract the padding mask from item id tensor it is expected to have 2 dims" in str(
        excinfo.value
    )
