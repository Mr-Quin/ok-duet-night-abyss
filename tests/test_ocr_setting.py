# OCR 设备开关：在启动时从存好的设置文件读，读不到就不用 NPU
import json
import os
import tempfile
import unittest

from src import config as C


class TestOcrSetting(unittest.TestCase):

    def test_npu_is_off_without_a_saved_setting(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(C.ocr_uses_npu(folder))
            with open(os.path.join(folder, C.OCR_CONFIG + '.json'), 'w', encoding='utf-8') as f:
                f.write('not json')
            self.assertFalse(C.ocr_uses_npu(folder))

    def test_the_saved_setting_turns_the_npu_on(self):
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, C.OCR_CONFIG + '.json'), 'w', encoding='utf-8') as f:
                json.dump({'使用NPU': True}, f, ensure_ascii=False)
            self.assertTrue(C.ocr_uses_npu(folder))


if __name__ == '__main__':
    unittest.main()
