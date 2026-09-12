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

"""App factory shared by the local runner and the deployer."""

from google.adk.apps.app import App

from common.config import APP_NAME

from .agent import root_agent


def create_app() -> App:
    """Wrap the root agent in an App.

    Kept bare on purpose. Context caching and events compaction are useful in
    a real agent but would only add moving parts to an integration probe.
    """
    return App(name=APP_NAME, root_agent=root_agent)
