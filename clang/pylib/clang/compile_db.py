#!/usr/bin/env python
# Copyright 2016 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import json
import os
import re
import shlex
import sys
import subprocess


_RSP_RE = re.compile(r' (@(.+?\.rsp)) ')
_debugging = False


def _ProcessEntry(entry):
  """Transforms one entry in the compile database to be clang-tool friendly."""
  # Escape backslashes to prevent shlex from interpreting them.
  escaped_command = entry['command'].replace('\\', '\\\\')
  split_command = shlex.split(escaped_command)
  # Drop gomacc.exe from the front, if present.
  if split_command[0].endswith('gomacc.exe'):
    split_command = split_command[1:]
  # Insert --driver-mode=cl as the first argument.
  split_command = split_command[:1] + ['--driver-mode=cl'] + split_command[1:]
  entry['command'] = ' '.join(split_command)

  # Expand the contents of the response file, if any.
  # http://llvm.org/bugs/show_bug.cgi?id=21634
  try:
    match = _RSP_RE.search(entry['command'])
    if match:
      rsp_path = os.path.join(entry['directory'], match.group(2))
      rsp_contents = file(rsp_path).read()
      entry['command'] = ''.join([
          entry['command'][:match.start(1)],
          rsp_contents,
          entry['command'][match.end(1):]])
  except IOError:
    if _debugging:
      print 'Couldn\'t read response file for %s' % entry['file']

  return entry


def _ProcessCompileDatabaseForWindows(compile_db):
  """Make the compile db generated by ninja on Windows more clang-tool friendly.

  Args:
    compile_db: The compile database parsed as a Python dictionary.

  Returns:
    A postprocessed compile db that clang tooling can use.
  """
  if _debugging > 0:
    print 'Read in %d entries from the compile db' % len(compile_db)
  compile_db = [_ProcessEntry(e) for e in compile_db]
  original_length = len(compile_db)

  # Filter out NaCl stuff. The clang tooling chokes on them.
  # TODO(dcheng): This doesn't appear to do anything anymore, remove?
  compile_db = [e for e in compile_db if '_nacl.cc.pdb' not in e['command']
      and '_nacl_win64.cc.pdb' not in e['command']]
  if _debugging > 0:
    print 'Filtered out %d entries...' % (original_length - len(compile_db))

  # TODO(dcheng): Also filter out multiple commands for the same file. Not sure
  # how that happens, but apparently it's an issue on Windows.
  return compile_db


def GetNinjaPath():
  ninja_executable = 'ninja.exe' if sys.platform == 'win32' else 'ninja'
  return os.path.join(
      os.path.dirname(os.path.realpath(__file__)),
        '..', '..', '..', '..', 'third_party', 'depot_tools', ninja_executable)


# FIXME: This really should be a build target, rather than generated at runtime.
def GenerateWithNinja(path):
  """Generates a compile database using ninja.

  Args:
    path: The build directory to generate a compile database for.

  Returns:
    A string containing the contents of the compile database.
  """
  # TODO(dcheng): Ensure that clang is enabled somehow.

  # First, generate the compile database.
  json_compile_db = subprocess.check_output([
      GetNinjaPath(), '-C', path, '-t', 'compdb', 'cc', 'cxx', 'objc',
      'objcxx'])
  compile_db = json.loads(json_compile_db)

  # TODO(dcheng): Ideally this would check target_os... but not sure there's an
  # easy way to do that, and (for now) cross-compiles don't work without custom
  # patches anyway.
  if sys.platform == 'win32':
    compile_db = _ProcessCompileDatabaseForWindows(compile_db)

  return json.dumps(compile_db, indent=2)


def Read(path):
  """Reads a compile database into memory.

  Args:
    path: Directory that contains the compile database.
  """
  with open(os.path.join(path, 'compile_commands.json'), 'rb') as db:
    return json.load(db)
