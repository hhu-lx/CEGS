# src/loaders/ts_loader.py
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional


class TimeSeriesDataLoader:
    def __init__(
        self,
        file_path: str,
        data_name: str = "数据",
        time_compression: float = 1.0,
        start_offset_seconds: int = 0,
    ):
        if time_compression <= 0:
            raise ValueError("time_compression must be positive")
        if start_offset_seconds < 0:
            raise ValueError("start_offset_seconds must be non-negative")
        self.file_path = Path(file_path)
        self.data_name = data_name
        self.data = None
        self.length = 0
        self.time_compression = time_compression
        self.start_offset_seconds = int(start_offset_seconds)
        self._load_data()

    def _load_data(self):
        if not self.file_path.exists():
            raise FileNotFoundError(f"文件不存在: {self.file_path}")

        # 读取CSV
        df = pd.read_csv(self.file_path, header=None, names=['value'])
        self.data = df['value'].values.astype(np.float64)
        self.data = np.nan_to_num(self.data, nan=0.0, posinf=0.0, neginf=0.0)
        self.length = len(self.data)

        print(f" 加载 {self.data_name}: {self.length} 个数据点")
        print(f"   原始值范围: {np.min(self.data):.4f} ~ {np.max(self.data):.4f}")

    def get_value_at_second(self, second: int) -> float:
        """获取指定秒数的数据值（超出边界返回边界值）"""
        if self.length == 0:
            return 0.0
        if second < 0:
            return self.data[0]
        elapsed_source_second = int(second / self.time_compression) if self.time_compression != 1.0 else second
        source_second = self.start_offset_seconds + elapsed_source_second
        if source_second >= self.length:
            return self.data[-1]
        return self.data[max(0, source_second)]

    def get_whole_data(self) -> np.ndarray:
        return self.data
