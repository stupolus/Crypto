"""Twitter pipeline для Layer 1 Sentiment input (план #17 §3.2).

Поток данных:
1. Apify Twitter Scraper polls аккаунты (см. бизнес/материалы/twitter-аккаунты.md)
2. GroqClient классифицирует tweets → TweetClassification (sentiment, tokens, relevance)
3. Aggregator группирует по token и time-window → SentimentSnapshot
4. SentimentAnalystAgent (Layer 3) использует SentimentSnapshot
"""

from parsers.twitter.aggregator import SentimentAggregator
from parsers.twitter.apify_scraper import ApifyScraperError, ApifyTwitterScraper
from parsers.twitter.groq_client import (
    GroqClient,
    GroqError,
    TweetClassification,
)
from parsers.twitter.models import SentimentSnapshot, Tweet

__all__ = [
    "ApifyScraperError",
    "ApifyTwitterScraper",
    "GroqClient",
    "GroqError",
    "SentimentAggregator",
    "SentimentSnapshot",
    "Tweet",
    "TweetClassification",
]
