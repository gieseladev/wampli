import re

import setuptools

# we can't import the module because we most certainly don't have all the
# dependencies installed. So let's just grab the text content and do some
# regex magic.
with open("libwampli/__init__.py", "r") as f:
    content = f.read()

# we're specifically interested in __magic__ attributes like __version__
# and __author__. This regex matches them and their raw values.
matches = re.findall(r"^(__\w+__) = (.+)$", content, re.MULTILINE)
# eval the raw value to get the Python rep
wampli = {key: eval(value) for key, value in matches}

with open("README.md", "r") as f:
    long_description = f.read()

setuptools.setup(
    name="wampli",
    version=wampli["__version__"],
    author=wampli["__author__"],
    author_email="team@giesela.dev",
    url="https://github.com/gieseladev/wampli",

    licence="MIT",
    long_description=long_description,
    long_description_content_type="text/markdown",

    packages=setuptools.find_packages(exclude=("docs", "tests")),

    python_requires="~=3.7",
    install_requires=[
        "aiobservable",
        "autobahn",
        "cbor",
        "konfi",
        "pyyaml",
        "yarl",
    ],

    entry_points={
        "console_scripts": [
            "wampli=wampli.cli:main",
        ],
    },
)
