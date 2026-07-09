import uuid
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
from app.config import settings


def save_chart(fig: plt.Figure) -> str:
    chart_id = str(uuid.uuid4())
    filepath = f"{settings.chart_dir}/{chart_id}.png"
    fig.savefig(filepath, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return filepath


def draw_bar(df: pd.DataFrame, x: str, y: str, title: str = "") -> str:
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.barplot(data=df, x=x, y=y, ax=ax, color="#7c3aed")
    ax.set_title(title or f"{y} by {x}")
    ax.tick_params(axis="x", rotation=45)
    return save_chart(fig)


def draw_line(df: pd.DataFrame, x: str, y: str, title: str = "") -> str:
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df[x], df[y], marker="o", color="#7c3aed")
    ax.set_title(title or f"{y} over {x}")
    ax.tick_params(axis="x", rotation=45)
    return save_chart(fig)


def draw_pie(df: pd.DataFrame, labels_col: str, values_col: str, title: str = "") -> str:
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.pie(df[values_col], labels=df[labels_col], autopct="%1.1f%%", startangle=90)
    ax.set_title(title or f"Distribution of {values_col}")
    return save_chart(fig)


def draw_scatter(df: pd.DataFrame, x: str, y: str, title: str = "") -> str:
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.scatter(df[x], df[y], alpha=0.6, color="#7c3aed")
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    ax.set_title(title or f"{y} vs {x}")
    return save_chart(fig)


def draw_heatmap(corr_df: pd.DataFrame, title: str = "") -> str:
    fig, ax = plt.subplots(figsize=(10, 8))
    sns.heatmap(corr_df, annot=True, cmap="Purples", ax=ax, fmt=".2f")
    ax.set_title(title or "Correlation Heatmap")
    return save_chart(fig)
