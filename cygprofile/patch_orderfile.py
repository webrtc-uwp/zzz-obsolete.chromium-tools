#!/usr/bin/python
# Copyright 2013 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Patch an orderfile.

Starting with a list of symbols in a binary and an orderfile (ordered list of
symbols), matches the symbols in the orderfile and augments each symbol with the
symbols residing at the same address (due to having identical code).

Note: It is possible to have.
- Several symbols mapping to the same offset in the binary.
- Several offsets for a given symbol (because we strip the ".clone." suffix)

TODO(lizeb): Since the suffix ".clone." is only used with -O3 that we don't
currently use, simplify the logic by removing the suffix handling.

The general pipeline is:
1. Get the symbol infos (offset, length, name) from the binary
2. Get the symbol names from the orderfile
3. Find the orderfile symbol names in the symbols coming from the binary
4. For each symbol found, get all the symbols at the same address
5. Output them to an updated orderfile, with several different prefixes
"""

import collections
import logging
import subprocess
import sys

# Prefixes for the symbols. We strip them from the incoming symbols, and add
# them back in the output file.
_PREFIXES = ('.text.startup.', '.text.hot.', '.text.unlikely.', '.text.')


SymbolInfo = collections.namedtuple('SymbolInfo', ['offset', 'size', 'name'])


def _RemoveClone(name):
  """Return name up to the ".clone." marker."""
  clone_index = name.find('.clone.')
  if clone_index != -1:
    return name[:clone_index]
  return name


def _GetSymbolInfosFromStream(nm_lines):
  """Parses the output of nm, and get all the symbols from a binary.

  Args:
    nm_lines: An iterable of lines

  Returns:
    The same output as GetSymbolsFromBinary.
  """
  # TODO(lizeb): Consider switching to objdump to simplify parsing.
  symbol_infos = []
  for line in nm_lines:
    # We are interested in two types of lines:
    # This:
    # 00210d59 00000002 t _ZN34BrowserPluginHostMsg_Attach_ParamsD2Ev
    # offset size <symbol_type> symbol_name
    # And that:
    # 0070ee8c T WebRtcSpl_ComplexBitReverse
    # In the second case we don't have a size, so use -1 as a sentinel
    parts = line.split()
    if len(parts) == 4:
      symbol_infos.append(SymbolInfo(
          offset=int(parts[0], 16), size=int(parts[1], 16), name=parts[3]))
    elif len(parts) == 3:
      symbol_infos.append(SymbolInfo(
          offset=int(parts[0], 16), size=-1, name=parts[2]))
  # Map the addresses to symbols.
  offset_to_symbol_infos = collections.defaultdict(list)
  name_to_symbol_infos = collections.defaultdict(list)
  for symbol in symbol_infos:
    symbol = SymbolInfo(symbol[0], symbol[1], _RemoveClone(symbol[2]))
    offset_to_symbol_infos[symbol.offset].append(symbol)
    name_to_symbol_infos[symbol.name].append(symbol)
  return (offset_to_symbol_infos, name_to_symbol_infos)


def _GetSymbolInfosFromBinary(binary_filename):
  """Runs nm to get all the symbols from a binary.

  Args:
    binary_filename: path to the binary.

  Returns:
    A tuple of collection.defaultdict:
    (offset_to_symbol_infos, name_to_symbol_infos):
    - offset_to_symbol_infos: {offset: [symbol_info1, ...]}
    - name_to_symbol_infos: {name: [symbol_info1, ...]}
  """
  command = 'nm -S -n %s | egrep "( t )|( W )|( T )"' % binary_filename
  p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
  try:
    result = _GetSymbolInfosFromStream(p.stdout)
    return result
  finally:
    p.wait()


def _GetSymbolsFromStream(lines):
  """Get the symbols from an iterable of lines.

  Args:
    lines: iterable of lines from an orderfile.

  Returns:
    Same as GetSymbolsFromOrderfile
  """
  # TODO(lizeb): Retain the prefixes later in the processing stages.
  symbols = []
  for line in lines:
    line = line.rstrip('\n')
    for prefix in _PREFIXES:
      if line.startswith(prefix):
        line = line[len(prefix):]
        break
    name = _RemoveClone(line)
    if name == '':
      continue
    symbols.append(line)
  return symbols


def _GetSymbolsFromOrderfile(filename):
  """Return the symbols from an orderfile.

  Args:
    filename: The name of the orderfile.

  Returns:
    A list of symbol names.
  """
  with open(filename, 'r') as f:
    return _GetSymbolsFromStream(f.xreadlines())


def _MatchProfiledSymbols(profiled_symbols, name_to_symbol_infos):
  """Filter name_to_symbol_infos with the keys from profiled_symbols.

  Args:
    profiled_symbols: Symbols to match
    name_to_symbol_infos: {name: [symbol_infos], ...}, as returned by
        GetSymbolInfosFromBinary

  Returns:
    A list of the symbol infos that have been matched.
  """
  found_symbols = 0
  missing_symbols = []
  symbol_infos = []
  for name in profiled_symbols:
    if name in name_to_symbol_infos:
      symbol_infos += name_to_symbol_infos[name]
      found_symbols += 1
    else:
      missing_symbols.append(name)
  logging.info('symbols found: %d\n' % found_symbols)
  if missing_symbols > 0:
    logging.warning('%d missing symbols.' % len(missing_symbols))
    missing_symbols_to_show = min(100, len(missing_symbols))
    logging.warning('First %d missing symbols:\n%s' % (
        missing_symbols_to_show,
        '\n'.join(missing_symbols[:missing_symbols_to_show])))
  return symbol_infos


def _ExpandSymbolsWithDupsFromSameOffset(symbol_infos, offset_to_symbol_infos):
  """Return the SymbolInfo sharing the same offset as those from symbol_infos.

  Args:
    symbol_infos: list of symbols to look for
    offset_to_symbol_infos: {offset: [symbol_info1, ...], ...}

  Returns:
    A list of matching symbol names
  """
  seen_offsets = set()
  matching_symbols = []
  for symbol in symbol_infos:
    if symbol.offset not in seen_offsets:
      seen_offsets.add(symbol.offset)
      matching_symbols += [
          s.name for s in offset_to_symbol_infos[symbol.offset]]
  return matching_symbols


def _PrintSymbolsWithPrefixes(symbol_names, output_file):
  """For each symbol, outputs it to output_file with the prefixes."""
  for name in symbol_names:
    output_file.write('\n'.join(prefix + name for prefix in _PREFIXES) + '\n')


def main(argv):
  if len(argv) != 3:
    print 'Usage: %s <unpatched_orderfile> <libchrome.so>' % argv[0]
    return 1
  orderfile_filename = argv[1]
  binary_filename = argv[2]
  (offset_to_symbol_infos, name_to_symbol_infos) = _GetSymbolInfosFromBinary(
      binary_filename)
  profiled_symbols = _GetSymbolsFromOrderfile(orderfile_filename)
  matched_symbols = _MatchProfiledSymbols(
      profiled_symbols, name_to_symbol_infos)
  symbols_by_offset = _ExpandSymbolsWithDupsFromSameOffset(
      matched_symbols, offset_to_symbol_infos)
  _PrintSymbolsWithPrefixes(symbols_by_offset, sys.stdout)
  # The following is needed otherwise Gold only applies a partial sort.
  print '.text'    # gets methods not in a section, such as assembly
  print '.text.*'  # gets everything else
  return 0


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  sys.exit(main(sys.argv))
