import numpy as np
import pandas as pd


class PolyFit:
    def __init__(self, order=1, gridsize=100):
        self.order = order
        self.gridsize = gridsize

    def __call__(self, data, groupby, orient, scales):
        return groupby.apply(data, self._fit_predict)

    def _fit_predict(self, data):
        x, y = data["x"], data["y"]
        if len(x) == 0:
            xx = yy = np.array([])
        else:
            # Drop missing/invalid values robustly
            mask = np.isfinite(x) & np.isfinite(y)
            x, y = x[mask], y[mask]
            if len(x) < 2:
                xx = yy = np.array([])
            else:
                p = np.polyfit(x, y, self.order)
                xx = np.linspace(x.min(), x.max(), self.gridsize)
                yy = np.polyval(p, xx)
        return pd.DataFrame({"x": xx, "y": yy})
