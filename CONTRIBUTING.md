# Contributing to Aether

Thanks for helping. Aether is deliberately small: one Python file, one HTML file,
no build step. Changes that keep it that way are the easiest to merge.

## Run it

```bash
./run.sh
```

That starts Ollama if needed, pulls the default models once, and opens the chat on
http://localhost:8100. See the [README](README.md) for the manual steps.

## Run the tests

```bash
python3 -m unittest discover -s tests -v
```

The tests use only the standard library and do not need Ollama: a stand-in server
plays its part. They run on every push and pull request (Python 3.9, 3.12, 3.13).

## Ground rules

- **No required dependencies.** `chat_server.py` must run on a stock Python 3.
  Optional extras, like voice input, must stay optional.
- **Local only.** The server talks to the Ollama on this machine and nothing else.
- **Add a test** when you change how a model is picked or what an endpoint returns.

## Sending a change

1. Fork the repo and create a branch.
2. Make the change and run the tests.
3. Open a pull request that says what changed and how you tried it.

Bugs and ideas are welcome as [issues](https://github.com/ZANYANBU/aether/issues).
