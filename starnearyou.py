"""Generate and tweet GIFs based on SDO imagery."""

import datetime
import json
import logging
import logging.handlers
import os
import tempfile
from time import sleep
import shutil
import subprocess
import urlparse

import click
import lxml.html
from PIL import Image
import requests
import twython


START = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)

SDO_URL_TEMPLATE = ("http://sdo.gsfc.nasa.gov/assets/img/browse/"
                    "{year:04d}/{month:02d}/{day:02d}/")

DEST_FILENAME_TEMPLATE = "{year:04d}_{month:02d}_{day:02d}_{hour:02d}.gif"

logger = logging.getLogger(__name__)

# === image fetching and making ===

def download_frame(url, download_dir):
    """Download the URL to a given directory, if it doesn't already exist."""
    filename = os.path.join(download_dir, split_url(url))

    try:
        with open(filename) as fp:
            logger.debug("Skipping frame: %s", url)
            logger.debug("File already exists: %s", filename)
    except IOError:
        logger.debug("File does not exist: %s", filename)
        logger.debug("Downloading frame: %s", url)
        sleep(.250)  # rate limit

        data = requests.get(url).content
        with open(filename, 'w') as fp:
            fp.write(data)

        logger.debug("Frame saved: %s", filename)
    finally:
        logger.debug("Downloaded and saved %s", url)
        return filename


def frame_urls(limit=32):
    """Yield the URLs of frames."""
    sdo_url = SDO_URL_TEMPLATE.format(year=START.year,
                                      month=START.month,
                                      day=START.day,
                                      hour=START.hour)

    logger.info("Fetching frames index: %s", sdo_url)
    sdo_index = lxml.html.parse(sdo_url).getroot()  # replace with requests fetching?
    sdo_index.make_links_absolute(sdo_url)

    link_tags = sdo_index.xpath("//a[contains(@href, '_1024_0193.jpg')]")
    logger.info("%s frame URLs found (limit: %s)", len(link_tags), limit)

    for link in link_tags[-1 * limit:]:
        yield link.get('href')


def convert_to_gif(frame_filenames, dest_filename):
    """Convert `frame_filenames` to an animated gif at path `dest_filename`."""
    logger.info("Converting %s frames to GIF", len(frame_filenames))

    convert_cmd = ['convert', '-delay', '15'] + \
                  [f for f in frame_filenames] + \
                  [dest_filename]
    subprocess.call(convert_cmd)

    logger.debug("Preliminary GIF saved: %s", dest_filename)


def optimize_gif(source, dest):
    logger.debug("Optimizing file size of %s", source)

    optimize_cmd = 'gifsicle --colors 256 --optimize=02 {0} > {1}'
    subprocess.call(optimize_cmd.format(source, dest), shell=True)

    logger.debug("Optimized GIF saved: %s", dest)


def process_image(filename):
    """Crop, rotate, and resize the image."""
    logger.debug("Cropping, rotating, and resizing %s", filename)
    with open(filename) as fp:
        image = Image.open(fp)

        origin = 0
        width = 1024
        height = 1024
        assert image.size == (width, height)

        crop_box = (
            origin,  # left
            origin + 72,  # top, except the first 72 pixels
            width - (width / 2),  # right, except second half
            height - 72, # bottom, except the last 72 pixels
        )
        image = image.crop(crop_box)

        # rotate for a funkier presentation, since GIFs get too big with the
        # full disk
        image = image.rotate(-90, Image.NEAREST, expand=True)

        # cut it down to near 440 x 220, which is optimal-ish for the Twitter
        # timeline
        # also, thumbnail works in place, rather than making a copy, for some
        # reason
        image.thumbnail((image.size[0] / 2, image.size[1] / 2), Image.LANCZOS)
    logger.debug("Cropped, rotated, and resized %s", filename)
    return image


def save_image(image, filename):
    """Save PIL/Pillow object to file."""
    with open(filename, 'w') as fp:
        image.save(fp)


def split_url(url):
    """Get the filename portion of a URL."""
    return os.path.basename(urlparse.urlparse(url).path)


def make_sun_gif(work_dir):
    """Fetch and make the latest Sun GIF in `work_dir`."""
    logger.info("Starting to generate a GIF")
    download_dir = os.path.join(work_dir, 'originals')
    gifs_dir = os.path.join(work_dir, 'gifs')

    urls = list(frame_urls())
    downloaded_filenames = (download_frame(url, download_dir) for url in urls)
    processed_images = (process_image(fname) for fname in downloaded_filenames)

    try:
        temp_dir = tempfile.mkdtemp()

        temp_files = []
        for image, url in zip(processed_images, urls):
            temp_file = os.path.join(temp_dir, split_url(url))
            save_image(image, temp_file)
            temp_files.append(temp_file)
        logger.info("%s frames processed", len(temp_files))

        dest_filename = DEST_FILENAME_TEMPLATE.format(year=START.year,
                                                      month=START.month,
                                                      day=START.day,
                                                      hour=START.hour)
        original_filename = os.path.join(temp_dir, dest_filename)
        final_filename = os.path.join(gifs_dir, dest_filename)

        convert_to_gif(temp_files, original_filename)
        optimize_gif(original_filename, final_filename)
        logger.info("Final GIF saved: %s", final_filename)
    finally:
        logger.debug("Cleaning up temporary files")
        shutil.rmtree(temp_dir)

    return final_filename


def configure_logging(filename=None, level=logging.INFO):
    logger.setLevel(min([logging.WARNING, level]))

    # log to screen
    console = logging.StreamHandler()
    console_formatter = logging.Formatter("%(levelname)s: %(message)s")
    console.setFormatter(console_formatter)
    console.setLevel(logging.WARNING)
    logger.addHandler(console)

    # log to file
    if filename is not None:
        logfile = logging.handlers.RotatingFileHandler(filename,
            maxBytes=5 * 10 ** 6, backupCount=4)
        file_fmt = "%(asctime)s - %(levelname)s - %(message)s"
        file_formatter = logging.Formatter(file_fmt)
        logfile.setFormatter(file_formatter)
        logfile.setLevel(level)
        logger.addHandler(logfile)


# === CLI stuff ===

def oauth_dance(ctx, param, value):
    """Set up OAuth."""
    if not value or ctx.resilient_parsing:
        return

    # set up
    try:
        auth_info = ctx.params['auth_info']
    except KeyError:
        click.echo("Error: --keyfile option is required to request access")
        ctx.exit(1)

    pre_auth_twitter = twython.Twython(auth_info['consumer_key'],
                                       auth_info['consumer_secret'])
    twitter_auth = pre_auth_twitter.get_authentication_tokens()

    # prompt user to go to web and get verifier code
    click.echo("Open: {}".format(twitter_auth['auth_url']))
    verifier = click.prompt("Please enter the code provided by Twitter")

    post_auth_twitter = twython.Twython(auth_info['consumer_key'],
                                        auth_info['consumer_secret'],
                                        twitter_auth['oauth_token'],
                                        twitter_auth['oauth_token_secret'])
    access_info = post_auth_twitter.get_authorized_tokens(verifier)

    click.echo("")
    click.echo("Access key: {}".format(access_info['oauth_token']))
    click.echo("Access secret: {}".format(access_info['oauth_token_secret']))
    ctx.exit()


def validate_keyfile(ctx, param, value):
    """Confirm that the keyfile contains valid JSON."""
    if value is not None:
        try:
            auth_info = json.load(value)['twitter']
        except:
            click.echo('A valid JSON keyfile is required!')
            raise
        return auth_info
    else:
        return value


def validate_dirs(ctx, param, value):
    """Confirm that the work directory has the right subdirectories."""
    if value is not None:
        originals = os.path.join(value, 'originals')
        gifs = os.path.join(value, 'gifs')

        if not all([os.path.isdir(originals), os.path.isdir(gifs)]):
            click.echo("Error: working directory requires "
                       "'originals' and 'gifs' subdirectories to exist!")
            ctx.exit(1)
    return value


def select_level(ctx, param, value):
    return {'debug': logging.DEBUG, 'info': logging.INFO}[value]

@click.command(help=__doc__)
@click.argument('work_dir', type=click.Path(exists=True, file_okay=False,
                                            dir_okay=True, writable=True,
                                            readable=True, resolve_path=True),
                envvar='STARNEARYOU_WORK_DIR', required=True,
                callback=validate_dirs)
@click.option('--keyfile', 'auth_info', type=click.File('r'),
              required=True, callback=validate_keyfile,
              help='JSON file with Twitter keys and secrets.')
@click.option('--logfile', type=click.Path(writable=True), default=None)
@click.option('--loglevel', type=click.Choice(['debug', 'info']),
              callback=select_level, default=None)
@click.option('--request-access', default=False, is_flag=True,
              callback=oauth_dance, expose_value=False,
              help='Request access key and secret.')
def cli(work_dir, tweet, auth_info, logfile, loglevel):
    configure_logging(logfile, loglevel)

    logger.debug("Command-line interface proccessed")
    with open(make_sun_gif(work_dir), 'rb') as fp:
        twitter = twython.Twython(auth_info['consumer_key'],
                                  auth_info['consumer_secret'],
                                  auth_info['access_key'],
                                  auth_info['access_secret'])

        attempts = 0
        limit = 3
        while True:
            try:
                attempts += 1
                media_id = twitter.upload_media(media=fp)[u'media_id']
                twitter.update_status(media_ids=[media_id])
                return
            except twython.exceptions.TwythonError as err:
                logger.exception("Tweeting failed: %r", err)
                if attempts < limit:
                    continue
                else:
                    break


if __name__ == '__main__':
    cli()
