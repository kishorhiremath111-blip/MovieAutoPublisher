#!/usr/bin/env python3
"""Exhaustively verify all topic recipes are reachable once and metadata is valid."""
import sys
from math import gcd

import topics


def main():
    if gcd(topics.STEP, topics.TOTAL) != 1:
        raise AssertionError("Topic step does not generate a complete permutation.")

    # Visit every index in the full recipe space, without rendering millions of videos.
    visited = bytearray(topics.TOTAL)
    for counter in range(topics.TOTAL):
        index = topics.index_for(counter)
        if visited[index]:
            raise AssertionError("Duplicate topic index %d at counter %d." % (index, counter))
        visited[index] = 1
        decoded = topics.decode(index)
        if decoded[0] >= len(topics.SCENES):
            raise AssertionError("Decoded scene index is out of range.")
    if visited.count(0):
        raise AssertionError("%d topic recipe indices were not reached." % visited.count(0))

    # Prove every scene label corresponds to a buildable generated topic.
    inverse_step = pow(topics.STEP, -1, topics.TOTAL)
    for scene_index, scene_name in enumerate(topics.SCENES):
        counter = ((scene_index - topics.OFFSET) * inverse_step) % topics.TOTAL
        topic = topics.build_topic(counter)
        if topic["params"]["scene"] != scene_name:
            raise AssertionError("Scene %s did not generate its expected recipe." % scene_name)
        if len(topic["title"]) > 100:
            raise AssertionError("YouTube title exceeds 100 characters.")
        if topic["params"]["multiplier"] != topic["multiplier"]:
            raise AssertionError("Multiplier metadata differs between recipe and topic.")

    # The first four counters must progress 1x, 2x, 4x, 8x in order.
    for stage, multiplier in enumerate((1, 2, 4, 8)):
        topic = topics.build_topic(stage)
        if topic["level"] != stage + 1 or topic["multiplier"] != multiplier:
            raise AssertionError("Expected Level %d / %dx progression." % (stage + 1, multiplier))

    print("PASS: all %d unique recipe indices are covered." % topics.TOTAL)
    print("PASS: all %d scene families are buildable." % len(topics.SCENES))
    print("PASS: Level 1-4 progression is 1x / 2x / 4x / 8x.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
