Star Near You
=============

[Star Near You](https://twitter.com/starnearyou) is a bot that's tweeting animated GIFs of the Sun's corona using data from a NASA spacecraft, the [Solar Dynamics Observatory](http://sdo.gsfc.nasa.gov/). It's scheduled to tweet three times a day, showing a time-lapse view of the Sun during the previous eight hours.

Star Near You helped to [inspire another bot maker to make an animated GIF bot that stays a little closer to Earth](http://52bots.tumblr.com/post/119334861589/14-rover-lapse-what-bot-that-keeps-up-with).


Acknowledgements
----------------

Thanks to NASA/SDO and the AIA, EVE, and HMI science teams for providing the data used in this project. Additional thanks to the attendees of [Bot Summit 2014](http://tinysubversions.com/botsummit/2014/) and the people of #botally, who answered my technical questions and provided inspiration.


Installation and configuration
------------------------------

To install and configure Star Near You:

  1. Run `pip install https://github.com/ddbeck/starnearyou`.
  2. Create a [Twitter API app](https://apps.twitter.com/) and put your API keys in a JSON file, like this:

     ```
     {
       "consumer_key": "consumer (api) key goes here",
       "consumer_secret":  "consumer (api) secret goes here",
       "oauth_token": "",
       "oath_token_secret": ""
     }
     ```
   
  3. Run `starnearyou --keyfile <path_to_keyfile> --request-access`, where `<path_to_keyfile>` is the path to the JSON file you created in the previous step.
  4. Follow the instructions shown. When you're finished, add the access key and secret to the JSON file.


Usage
-----

To tweet with Star Near You, run `starnearyou --keyfile <path_to_keyfile>`.


License
-------

You are free to use, copy, modify, and distribute this software under the terms of the MIT license, as long as you include the copyright and license notice. See the `LICENSE` file for details.

The data provided by NASA is a work of the United States government and is not copyrighted. See the Solar Dynamics Observatory page on [Data Rights and Rules for Data Use](http://sdo.gsfc.nasa.gov/data/rules.php) for details.