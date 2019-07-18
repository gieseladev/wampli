# WAMPli

A command line interface for the WAMP protocol.


## Introduction

WAMPli allows you to call procedures, publish to topics, and
subscribe to topics from the comfort of your console.

There's also a shell mode which starts an interactive console to 
conveniently perform all previously mentioned operations.


## Install

#### Using PIP

```bash
pip install wampli
```

#### Manually

First get the source code by either cloning the repo or downloading the
archive.

From here there are two ways to proceed.

###### Install using setup.py:

This is basically the same as installing it from PyPI,
but you can pass the `-e` flag to get an [editable install](https://pip.pypa.io/en/stable/reference/pip_install/#editable-installs).

1. Run `pip install .`

That's it.

###### Install using pipenv:

1. Install [pipenv](https://docs.pipenv.org/) using `pip install pipenv`
2. Install the dependencies using `pipenv install`.
3. You can now use `pipenv run wampli` to run wampli.
    Which is a shortcut for `pipenv run python -m wampli`


## Usage

WIP.
Use `wampli -h` to get some basic
help.