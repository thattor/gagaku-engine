from array import array
import unittest
from .excerpt_operation import CLIP_FRAMES, OVERLAP_FRAMES, STRIDE_FRAMES, chunks, finish_plan, request_checks

class OperationTests(unittest.TestCase):
    def test_request_boundaries_and_wait(self):
        for time,cycles,end in [(0,1,24),(7,1,24),(23.6-1/48000,1,24),(23.6-.25/48000,1,24),(23.6,2,47.6),(23.7,2,47.6),(300,13,307.2),(600,26,614)]:
            result=finish_plan(time)
            self.assertEqual((result['cycles'],result['end_seconds']),(cycles,end))
            self.assertFalse(result['verified_musical_exit']);self.assertFalse(result['tomede'])
            self.assertLessEqual(result['wait_seconds'],24)
        for index in range(1,26):
            boundary=index*STRIDE_FRAMES/48000
            for delta,cycles in [(-.25,index),(0,index+1),(.25,index+1)]:
                self.assertEqual(finish_plan(boundary+delta/48000)['cycles'],cycles)
        self.assertEqual(len(request_checks()),1083)
        for value in (-1,float('nan'),float('inf'),601,True):
            with self.assertRaises(ValueError):finish_plan(value)

    def test_stereo_overlap_uses_channel_frame_not_sample_index(self):
        source=array('f',[.2,.4])*CLIP_FRAMES
        result=list(chunks(source,2,2))
        self.assertEqual(sum(len(c) for c in result),2*(STRIDE_FRAMES+CLIP_FRAMES))
        join=result[1]
        for frame in (0,1,OVERLAP_FRAMES//2,OVERLAP_FRAMES-1):
            self.assertAlmostEqual(join[2*frame],.2,places=6)
            self.assertAlmostEqual(join[2*frame+1],.4,places=6)
        with self.assertRaises(ValueError):list(chunks(source,1,2))

    def test_one_cycle_preserves_source_pcm_and_zero_edges(self):
        source=array('f',[0])*CLIP_FRAMES;source[100]=.125
        output=list(chunks(source,1,1))
        self.assertEqual(output,[source])
        with self.assertRaises(ValueError):list(chunks(source,1,0))

if __name__=='__main__':unittest.main()
