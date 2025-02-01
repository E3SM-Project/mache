import requests


def download_file(url, local_filename):
    """
    Download a file from a URL.

    Parameters
    ----------
    url : str
        The URL of the file to download.
    local_filename : str
        The local path where the file will be saved.
    """
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(local_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
