workflow "run tests on commit" {
  on = "push"
  resolves = "run tests"
}

workflow "upload to PyPI on tag" {
  on = "push"
  resolves = [
    "filter tag",
    "upload to PyPI",
  ]
}

action "filter tag" {
  uses = "actions/bin/filter@master"
  args = "tag v*"
}

action "create distribution" {
  needs = "run tests"
  uses = "ross/python-actions/setup-py/3.7@master"
  args = "sdist"
}

action "upload to PyPI" {
  needs = "create distribution"
  uses = "ross/python-actions/twine@master"
  args = "upload ./dist/wampli*.tar.gz"
  secrets = [
    "TWINE_USERNAME",
    "TWINE_PASSWORD",
  ]
}

action "install dependencies" {
  uses = "gieseladev/python-actions@3.7"
  args = "pip install pipenv && pipenv install --dev"
}

action "run tests" {
  needs = "install dependencies"
  uses = "gieseladev/python-actions@3.7"
  args = "pipenv run tests"
}