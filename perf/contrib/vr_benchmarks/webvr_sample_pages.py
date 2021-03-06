# Copyright 2017 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from telemetry import story
from contrib.vr_benchmarks.vr_sample_page import VrSamplePage


class WebVrSamplePage(VrSamplePage):

  def __init__(self, page_set, url_parameters, extra_browser_args=None):
    super(WebVrSamplePage, self).__init__(
        sample_page='test-slow-render',
        page_set=page_set,
        url_parameters=url_parameters,
        extra_browser_args=extra_browser_args)

  def RunPageInteractions(self, action_runner):
    action_runner.TapElement(selector='canvas[id="webgl-canvas"]')
    action_runner.MeasureMemory(True)


class WebVrSamplePageSet(story.StorySet):
  """A page set using the official WebVR sample with settings tweaked."""

  def __init__(self):
    super(WebVrSamplePageSet, self).__init__()

    test_cases = [
      # Standard sample app with no changes
      ['canvasClickPresents=1', 'renderScale=1'],
      # Increased render scale
      ['canvasClickPresents=1', 'renderScale=1.5'],
      # Default render scale, increased load
      ['canvasClickPresents=1', 'renderScale=1', 'heavyGpu=1', 'cubeScale=0.2',
          'workTime=5'],
      # Further increased load
      ['canvasClickPresents=1', 'renderScale=1', 'heavyGpu=1', 'cubeScale=0.3',
          'workTime=10'],
      # Absurd load for fill-rate testing
      ['canvasClickPresents=1', 'renderScale=1.6', 'heavyGpu=1',
          'cubeScale=0.3', 'workTime=4'],
    ]

    for url_parameters in test_cases:
      # Standard set of pages with defaults
      self.AddStory(WebVrSamplePage(self, url_parameters))
      # Set of pages with standardized render size and VSync alignment disabled
      self.AddStory(WebVrSamplePage(self, url_parameters + ['standardSize=1'],
          extra_browser_args=['--disable-features=WebVrVsyncAlign']))
