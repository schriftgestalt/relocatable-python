# encoding: utf-8
#
# Copyright 2018 Greg Neagle.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Object to download the Python.org framework pkg and extract it"""

from __future__ import print_function

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

CURL = "/usr/bin/curl"
DITTO = "/usr/bin/ditto"
PKGUTIL = "/usr/sbin/pkgutil"
DEFAULT_BASEURL = "https://www.python.org/ftp/python/%s/python-%s-macosx%s.pkg"
DEFAULT_PYTHON_VERSION = "2.7.15"
DEFAULT_OS_VERSION = "10.9"
DEFAULT_CACHE_DIR = os.path.expanduser("~/Library/Caches/relocatable-python")


def sha256_of_file(path):
    """Returns the hex SHA-256 digest of the file at path."""
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


class FrameworkGetter(object):
    """Handles getting the Python.org pkg and extracting the framework"""

    downloaded_pkg_path = ""
    expanded_path = ""
    pkg_is_cached = False

    def __init__(
        self,
        python_version=DEFAULT_PYTHON_VERSION,
        os_version=DEFAULT_OS_VERSION,
        base_url=DEFAULT_BASEURL,
    ):
        self.python_version = python_version
        self.os_version = os_version
        self.base_url = base_url
        self.destination = ""

    def __del__(self):
        """Clean up"""
        if self.expanded_path and os.path.exists(self.expanded_path):
            shutil.rmtree(self.expanded_path)
        # Never delete a cached download; only clean up throwaway temp files.
        if self.downloaded_pkg_path and not self.pkg_is_cached:
            os.unlink(self.downloaded_pkg_path)

    def download(self):
        """Downloads a macOS installer pkg from python.org, caching it locally.

           The pkg is kept in a cache directory (override with the
           RELOCATABLE_PYTHON_CACHE environment variable). On repeated runs we
           ask python.org, via an If-Modified-Since request, whether a newer
           file is available: if not, the cached copy is reused untouched.
           The SHA-256 of the cached pkg is recorded alongside it.
           Returns path to the download."""
        if self.base_url == DEFAULT_BASEURL and \
           not self.os_version.startswith('10'):
            base_url = self.base_url.replace('macosx', 'macos')
        else:
            base_url = self.base_url
        url = base_url % (
            self.python_version,
            self.python_version,
            self.os_version,
        )

        cache_dir = os.environ.get("RELOCATABLE_PYTHON_CACHE", DEFAULT_CACHE_DIR)
        if not os.path.isdir(cache_dir):
            os.makedirs(cache_dir)
        cached_pkg = os.path.join(cache_dir, os.path.basename(url))

        # --remote-time stamps the cached file with the server's Last-Modified,
        # so the -z (If-Modified-Since) check on later runs is accurate.
        # A 304 (Not Modified) leaves the cached file in place.
        cmd = [CURL, "--fail", "--location", "--remote-time"]
        if os.path.exists(cached_pkg):
            cmd += ["-z", cached_pkg]
        cmd += ["-o", cached_pkg, "-w", "%{http_code}",
                "--silent", "--show-error", url]
        print("Checking %s..." % url)
        http_code = subprocess.check_output(cmd).decode("utf-8").strip()
        if http_code == "304":
            print("Server reports no newer file; using cached %s" % cached_pkg)
        else:
            print("Downloaded %s (HTTP %s)" % (cached_pkg, http_code))

        self.downloaded_pkg_path = cached_pkg
        self.pkg_is_cached = True

        digest = sha256_of_file(cached_pkg)
        with open(cached_pkg + ".sha256", "w") as handle:
            handle.write("%s  %s\n" % (digest, os.path.basename(cached_pkg)))
        print("SHA-256: %s" % digest)

    def expand(self):
        """Uses pkgutil to expand our downloaded pkg. Returns a path to the
           expanded contents."""
        self.expanded_path = os.path.join(
            tempfile.gettempdir(),
            os.path.basename(self.downloaded_pkg_path) + "__expanded__",
        )
        # pkgutil --expand requires the destination not to exist.
        if os.path.exists(self.expanded_path):
            shutil.rmtree(self.expanded_path)
        cmd = [
            PKGUTIL,
            "--expand",
            self.downloaded_pkg_path,
            self.expanded_path,
        ]
        print("Expanding %s..." % self.downloaded_pkg_path)
        subprocess.check_call(cmd)

    def extract_framework(self):
        """Extracts the Python framework from the expanded pkg"""
        payload = os.path.join(
            self.expanded_path, "Python_Framework.pkg/Payload"
        )
        cmd = [DITTO, "-xz", payload, self.destination]
        print("Extracting %s to %s..." % (payload, self.destination))
        subprocess.check_call(cmd)

    def download_and_extract(self, destination="."):
        """Downloads and extracts the Python framework.
           Returns path to the framework."""
        destination = os.path.expanduser(destination)
        if os.path.basename(destination) != "Python.framework":
            destination = os.path.join(destination, "Python.framework")
        if os.path.exists(destination):
            print(
                "Destination %s already exists!" % destination, file=sys.stderr
            )
            return None
        self.destination = destination
        try:
            self.download()
            self.expand()
            self.extract_framework()
            return destination
        except subprocess.CalledProcessError as err:
            sys.exit("%s" % err)
