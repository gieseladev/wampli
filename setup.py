import setuptools

import wampli

with open("README.md") as f:
    long_description = f.read()

setuptools.setup(
    name="wampli",
    version=wampli.__version__,
    author=wampli.__author__,
    author_email="team@giesela.dev",
    url="https://github.com/gieseladev/wampli",

    licence="MIT",
    long_description=long_description,
    long_description_content_type="text/markdown",

    packages=setuptools.find_packages(exclude=("docs", "tests")),

    python_requires="~=3.7",
    install_requires=[
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
