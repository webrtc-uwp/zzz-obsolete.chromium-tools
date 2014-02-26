// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "pure_virtual_trace.h"

namespace WebCore {

void B::trace(Visitor* visitor) {
    visitor->trace(m_a);
    // Is not required to trace base class A.
}

}
