build:
	rm -rf build
	./pages.py freeze

gh-pages:
	gittar -r ../ -b gh-pages 'file:build/*'

.PHONY: build
