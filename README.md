# Leetcode Anki card generator

## Summary
By running this script you'll be able to generate Anki cards with all the leetcode problems.

I personally use it to track my grinding progress.

## Installation
First initialize and activate python virtualenv somewhere
```
virtualenv -p python3 leetcode-anki
. leetcode-anki/bin/activate
```

Then initialize necessary environment variables. You can get the values directly from your browser
```
export LEETCODE_CSRF_TOKEN="xxx"
export LEETCODE_SESSION_ID="yyy"
```

And then run
```
make generate
```

You'll get `leetcode.apkg` file, which you can import directly to your anki app.
