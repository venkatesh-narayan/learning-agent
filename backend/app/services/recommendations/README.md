See [the main README](https://github.com/venkatesh-narayan/learning-agent/blob/main/README.md) for more information on the overall flow.
`orchestrator.py` discusses the main flow - specifically the `get_recommendations` function. `process_with_progress` is basically the same as `get_recommendations`, but uses websockets to tell the frontend which step we're currently on in the flow.
In order to run this locally on your terminal, you can run `tests/test_recommendations.py`. You'll need to set up MongoDB.
