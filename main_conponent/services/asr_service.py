from dashscope.audio.asr import TranslationRecognizerChat, TranslationRecognizerCallback
from dashscope.audio.asr import TranscriptionResult, TranslationResult
import logging

# 设置日志
logger = logging.getLogger(__name__)

class ASRCallback(TranslationRecognizerCallback):
    def __init__(self):
        self.final_text = ""
        self.error = None
        self.is_finished = False
        self.is_sentence_end = False
        self.all_text = []  # 存储所有的中间结果
        
    def on_open(self) -> None:
        logger.info('语音识别开始')
        self.is_finished = False
        self.is_sentence_end = False
        self.all_text = []

    def on_close(self) -> None:
        logger.info('语音识别结束')
        self.is_finished = True
        # 合并所有结果
        if self.all_text:
            self.final_text = self.all_text[-1]

    def on_error(self, error):
        logger.error(f'语音识别错误: {error}')
        self.error = error
        self.is_finished = True

    def on_event(
        self,
        request_id,
        transcription_result: TranscriptionResult,
        translation_result: TranslationResult,
        usage,
    ) -> None:
        logger.info(f'收到事件: request_id={request_id}')
        if transcription_result is not None:
            logger.info(f'转录结果: {transcription_result.text}')
            if transcription_result.text:
                self.all_text.append(transcription_result.text)
                self.final_text = transcription_result.text
                if hasattr(transcription_result, 'is_sentence_end') and transcription_result.is_sentence_end:
                    self.is_sentence_end = True
                    logger.info('句子结束')
        else:
            logger.warning('没有转录结果')