
test_general_requirements:
	$(info >>> Testing General Requirements)
	sage helpers/check_requirements.py

test_doctests:
	$(info >>> Testing Python Doctests)
	export SAGE_PATH=$Z3/src/api/python:.
	sage -t helpers/miscs.py

all: test_general_requirements test_doctests
	$(info >>> All Done)


# SUBDIRS := $(wildcard */.)

# all: $(SUBDIRS)
# $(SUBDIRS):
# 	$(MAKE) -C $@

# .PHONY: all $(SUBDIRS)

clean:
	rm -rf CIVLREP
	rm -rf *.pyo *.pyc *~
	rm -rf data/*.pyo data/*.pyc data/*~
	rm -rf data/invs/*.pyo data/invs/*.pyc data/invs/*~
	rm -rf data/poly/*.pyo data/poly/*.pyc data/poly/*~
	rm -rf cegir/*.pyo cegir/*.pyc cegir/*~
