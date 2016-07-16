"""Generate and tweet GIFs based on SDO imagery."""

import datetime
import json
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


# === image fetching and making ===

def download_frame(url, download_dir):
    """Download the URL to a given directory, if it doesn't already exist."""
    filename = os.path.join(download_dir, split_url(url))

    try:
        with open(filename) as fp:
            pass  # if no IOError, it's already downloaded
        return filename
    except IOError:
        sleep(1)
        data = requests.get(url).content
        with open(filename, 'w') as fp:
            fp.write(data)
        return filename


def frame_urls(limit=32):
    """Yield the URLs of frames."""
    sdo_url = SDO_URL_TEMPLATE.format(year=START.year,
                                      month=START.month,
                                      day=START.day,
                                      hour=START.hour)
    sdo_index = lxml.html.parse(sdo_url).getroot()
    sdo_index.make_links_absolute(sdo_url)
    link_tags = sdo_index.xpath("//a[contains(@href, '_1024_0193.jpg')]")

    for link in link_tags[-1 * limit:]:
        yield link.get('href')


def convert_to_gif(frame_filenames, dest_filename):
    """Convert `frame_filenames` to an animated gif at path `dest_filename`."""
    convert_cmd = ['convert', '-delay', '15'] + \
                  [f for f in frame_filenames] + \
                  [dest_filename]
    subprocess.call(convert_cmd)


def optimize_gif(source, dest):
    optimize_cmd = 'gifsicle --colors 256 --optimize=03 {0} > {1}'
    subprocess.call(optimize_cmd.format(source, dest), shell=True)


def process_image(filename):
    """Crop and rotate the image."""
    with open(filename) as fp:
        image = Image.open(fp)

        sun = image.crop((0, 75, 1024, 1024 - 75))
        timestamp = image.crop((0, 985, 1024, 1024 - 15))

        mode = sun.mode
        width = sun.size[0]
        height = sun.size[1] + timestamp.size[1]

        final = Image.new(mode, (width, height))
        final.paste(sun, (0, 0))
        final.paste(timestamp, (0, sun.size[1]))

        final.thumbnail((final.size[0] * .95, final.size[1] * .95), Image.LANCZOS)
    return final


def save_image(image, filename):
    """Save PIL/Pillow object to file."""
    with open(filename, 'w') as fp:
        image.save(fp)


def split_url(url):
    """Get the filename portion of a URL."""
    return os.path.basename(urlparse.urlparse(url).path)


def make_sun_gif(work_dir):
    """Fetch and make the latest Sun GIF in `work_dir`."""
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

        dest_filename = DEST_FILENAME_TEMPLATE.format(year=START.year,
                                                      month=START.month,
                                                      day=START.day,
                                                      hour=START.hour)
        original_filename = os.path.join(temp_dir, dest_filename)
        final_filename = os.path.join(gifs_dir, dest_filename)

        convert_to_gif(temp_files, original_filename)
        optimize_gif(original_filename, final_filename)
    finally:
        shutil.rmtree(temp_dir)

    return final_filename


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


@click.command(help=__doc__)
@click.argument('work_dir', type=click.Path(exists=True, file_okay=False,
                                            dir_okay=True, writable=True,
                                            readable=True, resolve_path=True),
                envvar='STARNEARYOU_WORK_DIR', required=True,
                callback=validate_dirs)
@click.option('--keyfile', 'auth_info', type=click.File('r'),
              required=True, callback=validate_keyfile,
              help='JSON file with Twitter keys and secrets.')
@click.option('--request-access', default=False, is_flag=True,
              callback=oauth_dance, expose_value=False,
              help='Request access key and secret.')
@click.option('--tweet/--no-tweet', default=True)
def cli(work_dir, auth_info, tweet):
    with open(make_sun_gif(work_dir), 'rb') as fp:
        twitter = twython.Twython(auth_info['consumer_key'],
                                  auth_info['consumer_secret'],
                                  auth_info['access_key'],
                                  auth_info['access_secret'])

        if not tweet:
            click.echo("File created: {}".format(fp.name))

        retries = 0
        while tweet:
            try:
                media_id = twitter.upload_media(media=fp)[u'media_id']
                twitter.update_status(media_ids=[media_id])
            except twython.exceptions.TwythonError:
                if retries >= 3:
                    break
                else:
                    retries += 1
                    continue


if __name__ == '__main__':
    cli()
