# Copyright (c) 2012 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
import os
import subprocess

class FileServer(object):
  def __init__(self, path, port=8000):
    assert os.path.exists(path)
    if os.path.isdir(path):
      self._path = path
    else:
      self._path = os.path.dirname(path)
    self._port = port

  def __enter__(self):
    self._server = subprocess.Popen(
        ['python', '-m', 'SimpleHTTPServer', str(self._port)],
        cwd=self._path)
    return 'http://localhost:%d' % self._port

  def __exit__(self, *args):
    self._server.kill()
    self._server = None

  def __del__(self):
    if self._server:
      self._server.kill()
