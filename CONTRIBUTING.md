# Contributing

The highest-value contribution is a new adapter for a real government source —
see [`docs/ADDING_A_SOURCE.md`](docs/ADDING_A_SOURCE.md) and
[`docs/SOURCES.md`](docs/SOURCES.md) (which lists sources already investigated,
including dead ends, so you don't repeat that work).

## Ground rules

1. No dependency for the sake of convenience. The pipeline runs on the Python
   standard library so `git clone && python3 -m pipeline.run all` works with
   nothing installed. If an adapter genuinely needs a PDF library, add it to
   `requirements.txt` as optional and make the rest of the pipeline still work
   without it.
2. Run the tests before opening a PR: `python3 -m unittest discover -s tests`.
3. Never commit an API key, even a "free public sample" one referenced in a
   source's own docs. Put the registration instructions in `docs/SOURCES.md`
   instead.
4. If you find a new source, write down what you verified in
   `docs/SOURCES.md` — including what did NOT work. A dead end saved someone
   else's afternoon is as valuable as a working adapter.
5. See [`docs/LEGAL.md`](docs/LEGAL.md) before adding anything that touches
   personal data (landowner names, individual contact details) or before
   phrasing anything as investment advice.

## Local setup

There isn't one, on purpose. Python 3.9+ is the only requirement.

```bash
git clone https://github.com/dizzybot31/untitled-infra-tracker.git
cd untitled-infra-tracker
python3 -m unittest discover -s tests
python3 -m pipeline.run all
python3 -m http.server 8777    # then open http://localhost:8777/web/
```
