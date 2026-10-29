import unittest

from src.ui import anim


class FakeRoot:
    """Collects `after` callbacks so tests can step frames by hand."""

    def __init__(self):
        self.jobs = {}
        self.next_id = 0

    def after(self, _ms, callback):
        self.next_id += 1
        self.jobs[self.next_id] = callback
        return self.next_id

    def after_cancel(self, job):
        self.jobs.pop(job, None)

    def run_pending(self):
        jobs, self.jobs = self.jobs, {}
        for callback in jobs.values():
            callback()


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class EasingTests(unittest.TestCase):
    def test_easings_hit_endpoints(self):
        for easing in (anim.linear, anim.ease_out_cubic, anim.ease_in_out, anim.ease_out_back):
            self.assertAlmostEqual(easing(0.0), 0.0)
            self.assertAlmostEqual(easing(1.0), 1.0)

    def test_lerp_color(self):
        self.assertEqual(anim.lerp_color("#000000", "#FFFFFF", 0.0), "#000000")
        self.assertEqual(anim.lerp_color("#000000", "#FFFFFF", 1.0), "#ffffff")
        self.assertEqual(anim.lerp_color("#000000", "#FF0080", 0.5), "#800040")


class AnimatorTests(unittest.TestCase):
    def setUp(self):
        self.root = FakeRoot()
        self.clock = FakeClock()
        self.animator = anim.Animator(self.root, clock=self.clock)

    def step(self, seconds):
        self.clock.now += seconds
        self.root.run_pending()

    def test_runs_to_completion_and_calls_on_done(self):
        values, done = [], []
        self.animator.animate("a", 100, values.append, easing=anim.linear, on_done=lambda: done.append(True))
        self.step(0.05)
        self.step(0.06)
        self.assertAlmostEqual(values[0], 0.5)
        self.assertEqual(values[-1], 1.0)
        self.assertEqual(done, [True])
        self.assertFalse(self.animator.is_running("a"))
        self.assertEqual(self.root.jobs, {})  # loop goes idle once nothing runs

    def test_same_key_replaces_running_animation(self):
        first, second = [], []
        self.animator.animate("k", 100, first.append)
        self.animator.animate("k", 100, second.append)
        self.step(0.2)
        self.assertEqual(first, [])
        self.assertEqual(second, [1.0])

    def test_cancel_all_stops_everything(self):
        values = []
        self.animator.animate("a", 100, values.append)
        self.animator.animate("b", 100, values.append, loop=True)
        self.animator.cancel_all()
        self.step(0.2)
        self.assertEqual(values, [])
        self.assertEqual(self.root.jobs, {})

    def test_reduce_motion_jumps_to_end(self):
        values, done = [], []
        self.animator.reduce_motion = True
        self.animator.animate("a", 500, values.append, on_done=lambda: done.append(True))
        self.animator.animate("pulse", 500, values.append, loop=True)
        self.assertEqual(values, [1.0, 0.0])
        self.assertEqual(done, [True])
        self.assertEqual(self.root.jobs, {})

    def test_loop_wraps_until_cancelled(self):
        values = []
        self.animator.animate("pulse", 100, values.append, easing=anim.linear, loop=True)
        self.step(0.15)
        self.assertAlmostEqual(values[-1], 0.5)
        self.assertTrue(self.animator.is_running("pulse"))
        self.animator.cancel("pulse")
        self.step(0.1)
        self.assertEqual(len(values), 1)

    def test_delay_holds_animation(self):
        values = []
        self.animator.animate("a", 100, values.append, easing=anim.linear, delay_ms=100)
        self.step(0.05)
        self.assertEqual(values, [])
        self.step(0.1)
        self.assertAlmostEqual(values[-1], 0.5)

    def test_destroyed_widget_drops_animation(self):
        import tkinter as tk

        def broken(_t):
            raise tk.TclError("invalid command name")

        self.animator.animate("a", 100, broken)
        self.step(0.05)
        self.assertFalse(self.animator.is_running("a"))


if __name__ == "__main__":
    unittest.main()
