base:
	# You have to set the variables below in order to
	# authenticate on leetcode. It is required to read
	# the information about the problems
	test ! "x${VIRTUAL_ENV}" = "x" || (echo "Need to run inside venv" && exit 1)
	pip install -r requirements.txt

generate: base ## Generate cards without user submission but for all problems available.
	python3 generate.py
	@echo "\033[0;32mSuccess! Now you can import leetcode.apkg to Anki.\033[0m"

generate-with-last-submissions: base ## Generate cards with user last submissions for only solved problems
	python3 generate.py --problem-status AC --include-last-submission True
	@echo "\033[0;32mSuccess! Now you can import leetcode.apkg to Anki.\033[0m"

help: ## List makefile targets
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'
