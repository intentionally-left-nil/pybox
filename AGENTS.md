# pybox

pybox is a security sandbox for Python environments used by AI agents. It replaces `python` and `pip` binaries with wrappers that enforce strict filesystem restrictions via [nono](https://nono.sh): write access is limited to the current directory, reads are scoped to the environment, and pip installs cannot pollute global state.

Before making architecture or product decisions, read [docs/overview.md](docs/overview.md). When considering a change to the nono policy or have questions about how the sandbox works, read [docs/nono_research.md](docs/nono_research.md) or the nono reference at https://nono.sh/llms.txt.
