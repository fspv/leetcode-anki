generate:
	# You have to set the variables below in order to
	# authenticate on leetcode. It is required to read
	# the information about the problems
	test ! "x${VIRTUAL_ENV}" = "x" || (echo "Need to run inside venv" && exit 1)
	pip install -r requirements.txt
	python3 generate.py
