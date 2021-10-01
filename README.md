# Leetcode Anki card generator

## Summary
By running this script you'll be able to generate Anki cards with all the leetcode problems.

I personally use it to track my grinding progress.

![ezgif-7-03b29041a91e](https://user-images.githubusercontent.com/1616237/134259809-57af6afb-8885-4899-adf8-a2639977baeb.gif)

![photo_2021-09-29_08-58-19 jpg 2](https://user-images.githubusercontent.com/1616237/135676120-6a83229d-9715-45fb-8f85-1b1b27d96f9b.png)
![photo_2021-09-29_08-58-21 jpg 2](https://user-images.githubusercontent.com/1616237/135676123-106871e0-bc8e-4d23-acef-c27ebe034ecf.png)
![photo_2021-09-29_08-58-23 jpg 2](https://user-images.githubusercontent.com/1616237/135676125-90067ea3-e111-49da-ae13-7bce81040c37.png)


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

There also will be a `cache` directory created for the cached data about the problems. If you want to fetch more up to date information about the existing problems, delete this dir. Just keep in mind, it'll take a while to re-download the data about all the problems.
