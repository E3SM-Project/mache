(dev-building-docs)=

# Building the Documentation

As long as you have followed the procedure in {ref}`dev-installing-mache` for 
setting up your conda environment, you will already have the packages available
that you need to build the documentation.

Then, run the following script to build the docs:

```bash
cd docs
DOCS_VERSION=test make clean versioned-html
```

You can view the documentation by opening `_build/html/index.html`.
