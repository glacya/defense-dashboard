"""Python 3.10/SciPy 1.15에서도 사용하는 Welch·Games–Howell 계산."""
from types import SimpleNamespace

import numpy as np
from scipy.stats import studentized_range
from statsmodels.stats.oneway import anova_oneway


def welch_anova(*groups):
    result = anova_oneway(groups, use_var='unequal', welch_correction=True)
    return float(result.statistic), float(result.pvalue)


def games_howell(groups, confidence=0.95):
    means = np.array([np.mean(g) for g in groups])
    sizes = np.array([len(g) for g in groups])
    if (sizes < 2).any():
        raise ValueError('Games–Howell 검정은 그룹마다 최소 2명이 필요합니다.')
    variances = np.array([np.var(g, ddof=1) for g in groups]) / sizes
    if (variances <= 0).any():
        raise ValueError('Games–Howell 검정은 양의 그룹 분산이 필요합니다.')
    difference = means[:, None] - means[None, :]
    total = variances[:, None] + variances[None, :]
    degrees = total**2 / ((variances**2/(sizes-1))[:, None]
                          + (variances**2/(sizes-1))[None, :])
    scale = np.sqrt(total/2)
    pvalue = studentized_range.sf(np.abs(difference)/scale, len(groups), degrees)
    margin = studentized_range.ppf(confidence, len(groups), degrees)*scale
    return SimpleNamespace(statistic=difference, pvalue=pvalue,
                           low=difference-margin, high=difference+margin)
