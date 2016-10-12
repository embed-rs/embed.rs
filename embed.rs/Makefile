build:
	rm -rf build
	./pages.py freeze
	echo embed.rs > build/CNAME

gh-pages: build
	gittar -r ../ -b gh-pages 'file:build/*'

publish: gh-pages
	git push -f origin gh-pages

.PHONY: build gh-pages publish
