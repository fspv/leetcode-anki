# Leetcode Anki card generator

## Summary
By running this script you'll be able to generate Anki cards with all the leetcode problems.

I personally use it to track my grinding progress.

![ezgif-7-03b29041a91e](https://user-images.githubusercontent.com/1616237/134259809-57af6afb-8885-4899-adf8-a2639977baeb.gif)

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

There also will be the `cache` directory created for the cached data about the problems. In you want to fetch more up to date version about the existing problems, delete this dir. Just keep in mind, it'll take a while to re-download the data about all the problems.

## Known issues
The script doesn't exit on finish.

This is the result of a swagger bug, that has never been addressed https://github.com/swagger-api/swagger-codegen/issues/9991

As a workaround I generarate a new anki board after each question added. So when progressbar is full, just kill the app. Generation of `leetcode.apkg` file will be complete by this point. This is not effective, so should be fixed later.
