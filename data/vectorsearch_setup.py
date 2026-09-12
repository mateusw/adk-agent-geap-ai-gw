#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Not an official Google product. Demonstration code only: it may
# contain bugs and is not intended for production use.

"""Create the Agent Retrieval collection and load the synthetic catalog.

The collection declares a ``content_embedding`` vector field with a
``vertexEmbeddingConfig``, so the service embeds each object server-side from
the ``textTemplate`` below. Objects are therefore inserted with empty
``vectors`` — we never compute an embedding ourselves, on write or on read.

Idempotent: re-running reuses an existing collection and overwrites objects by
their SKU.

Usage:
    python data/vectorsearch_setup.py
"""

from __future__ import annotations

import json
import os
import sys

from dotenv import load_dotenv

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
load_dotenv(os.path.join(_ROOT, ".env"))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from google.api_core.exceptions import AlreadyExists  # noqa: E402
from google.cloud import vectorsearch_v1beta  # noqa: E402

from common.config import (  # noqa: E402
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    PROJECT_ID,
    VS_COLLECTION_ID,
    VS_EMBED_FIELD,
    vs_collection_parent,
    vs_location_parent,
)

_BATCH_SIZE = 20

DATA_SCHEMA = {
    "type": "object",
    "properties": {
        "sku": {"type": "string"},
        "name": {"type": "string"},
        "category": {"type": "string"},
        "material": {"type": "string"},
        "room": {"type": "string"},
        "description": {"type": "string"},
        "price_usd": {"type": "number"},
    },
}

# RETRIEVAL_DOCUMENT on write pairs with QUESTION_ANSWERING on read. The
# template decides what actually gets embedded — price is deliberately left
# out, since a number contributes noise to a semantic match.
VECTOR_SCHEMA = {
    VS_EMBED_FIELD: {
        "dense_vector": {
            "dimensions": EMBEDDING_DIMENSIONS,
            "vertex_embedding_config": {
                "model_id": EMBEDDING_MODEL,
                "task_type": "RETRIEVAL_DOCUMENT",
                "text_template": (
                    "{name}\n"
                    "Category: {category}\n"
                    "Material: {material}\n"
                    "Room: {room}\n"
                    "{description}"
                ),
            },
        }
    }
}


def create_collection() -> None:
    client = vectorsearch_v1beta.VectorSearchServiceClient()
    request = vectorsearch_v1beta.CreateCollectionRequest(
        parent=vs_location_parent(),
        collection_id=VS_COLLECTION_ID,
        collection={
            "data_schema": DATA_SCHEMA,
            "vector_schema": VECTOR_SCHEMA,
        },
    )
    try:
        operation = client.create_collection(request=request)
        print(f"Creating collection '{VS_COLLECTION_ID}' (waiting for LRO)...")
        operation.result()
        print("Collection created.")
    except AlreadyExists:
        print(f"Collection '{VS_COLLECTION_ID}' already exists — reusing.")


def load_products() -> None:
    client = vectorsearch_v1beta.DataObjectServiceClient()
    parent = vs_collection_parent()

    with open(os.path.join(_HERE, "catalog.json")) as f:
        products = json.load(f)

    total = 0
    for start in range(0, len(products), _BATCH_SIZE):
        chunk = products[start : start + _BATCH_SIZE]
        requests = [
            vectorsearch_v1beta.CreateDataObjectRequest(
                parent=parent,
                data_object_id=p["sku"],
                # Empty vectors => the service auto-embeds via the schema.
                data_object={"data": p, "vectors": {}},
            )
            for p in chunk
        ]
        batch = vectorsearch_v1beta.BatchCreateDataObjectsRequest(
            parent=parent, requests=requests
        )
        client.batch_create_data_objects(request=batch)
        total += len(chunk)
        print(f"Inserted {total}/{len(products)} products...")

    print(f"Loaded {total} products into '{VS_COLLECTION_ID}'.")


def main() -> None:
    if not PROJECT_ID:
        sys.exit("ERROR: GOOGLE_CLOUD_PROJECT is not set (check .env).")
    create_collection()
    load_products()
    print(
        "\nDone. Embeddings are generated asynchronously — allow a short wait"
        " before the first search returns results."
    )


if __name__ == "__main__":
    main()
