#!/usr/bin/env python3
"""Exhaustively verify the topic index permutation and representative recipe metadata."""
import sys
from math import gcd

import topics


def main():
    if gcd(topics.STEP, topics.TOTAL) != 1:
        raise AssertionError("Topic step does not generate a complete permutation.")

    # Every supported counter must map to one distinct recipe index exactly once.
    visited = bytearray(topics.TOTAL)
    for counter in range(topics.TOTAL):
        index = topics.index_for(counter)
        if visited[index]:
            raise AssertionError("Duplicate topic index %d at counter %d." % (index, counter))
        visited[index] = 1
    if not all(visited):
        raise AssertionError("Not every recipe index was visited.")

    # Exercise every generated scene and all four progression states.
    for scene_index, scene in enumerate(topics.SCENES):
        for stage, multiplier in enumerate((1, 2, 4, 8)):
            counter = (scene_index * 9973 + stage) % topics.TOTAL
            topic = topics.build_topic(counter)
            if topic["params"]["scene"] not in topics.SCENES:
                raise AssertionError("Unknown scene in generated recipe.")
            if len(topic["title"]) > 100:
                raise AssertionError("YouTube title exceeds 100 characters.")
            if topic["level"] != stage + 1 and topic["multiplier"] != multiplier:
                # The counter's level cycles globally; explicitly verify a matching counter below.
                pass

    for stage, multiplier in enumerate((1, 2, 4, 8)):
        topic = topics.build_topic(stage)
        if topic["level"] != stage + 1 or topic["multiplier"] != multiplier:
            raise AssertionError("Level/multiplier progression is not 1x/2x/4x/8x.")

    if topics.SCENES[-1] != "gaprun" or topics.SCENE_NAMES["gaprun"] != "Multiplier Gap Run":
        raise AssertionError("New gap-run scene is missing from topic catalogue.")

    print("PASS: all %d topic indices are unique and covered." % topics.TOTAL)
    print("PASS: %d scene families and 1x/2x/4x/8x levels registered." % len(topics.SCENES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
