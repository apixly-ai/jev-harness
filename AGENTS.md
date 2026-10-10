# Jev Harness contributor instructions

Use a virtual environment. Write a failing behavioral test before runtime changes.
Keep observation, context admission, Jev decisions, tool execution and verification separate.
Jev may choose only registered tools and program-supplied parameter candidates.
Model output never becomes executable code, selectors, commands or unvetted arguments.
Preserve uncertain execution and unknown usage. No result caching. Maximum inference concurrency 30.
Use synthetic inputs for tests. Live tests require opt-in and a supplied credential.
Use headless Camofox for browser acceptance; preserve named sessions and close only task tabs.
Never commit credentials, private data, maintainer paths or local browser state.
Run lint, coverage, package build, offline A/B and public-content checks before publishing.
Keep bilingual claims aligned. Mock success is not live success; submission is not completion.
