"""Tests for the custom BinaryMinHeap Priority Queue."""
import random
from django.test import SimpleTestCase

from navigation.utils.graph import BinaryMinHeap


class BinaryMinHeapTest(SimpleTestCase):
    def test_empty_heap(self):
        heap = BinaryMinHeap()
        self.assertTrue(heap.is_empty())
        self.assertEqual(len(heap), 0)
        with self.assertRaises(IndexError):
            heap.pop()
        with self.assertRaises(IndexError):
            heap.peek()

    def test_single_element(self):
        heap = BinaryMinHeap()
        heap.push(10.5, 1)
        self.assertFalse(heap.is_empty())
        self.assertEqual(len(heap), 1)
        self.assertEqual(heap.peek()[0], 10.5)
        self.assertEqual(heap.peek()[1], 1)

        val = heap.pop()
        self.assertEqual(val[0], 10.5)
        self.assertEqual(val[1], 1)
        self.assertTrue(heap.is_empty())

    def test_sorted_order_extraction(self):
        heap = BinaryMinHeap()
        elements = [(5.0, 5), (1.0, 1), (9.0, 9), (3.0, 3), (2.0, 2), (8.0, 8)]
        for prio, item in elements:
            heap.push(prio, item)

        self.assertEqual(len(heap), len(elements))
        extracted = []
        while not heap.is_empty():
            extracted.append(heap.pop()[0])

        self.assertEqual(extracted, [1.0, 2.0, 3.0, 5.0, 8.0, 9.0])

    def test_random_stress_invariant(self):
        heap = BinaryMinHeap()
        rng = random.Random(12345)
        values = [rng.uniform(-500.0, 500.0) for _ in range(200)]
        for v in values:
            heap.push(v, int(v))

        extracted = []
        while not heap.is_empty():
            extracted.append(heap.pop()[0])

        self.assertEqual(extracted, sorted(values))

    def test_snapshot(self):
        heap = BinaryMinHeap()
        heap.push(15.0, 1)
        heap.push(5.0, 2)
        heap.push(10.0, 3)

        snap = heap.snapshot()
        self.assertEqual(snap, [(5.0, 2), (10.0, 3), (15.0, 1)])

