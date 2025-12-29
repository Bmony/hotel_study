#!/bin/bash

# Hotels 인덱스 생성
curl -X PUT "localhost:9200/hotels" -H 'Content-Type: application/json' -d'
{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "analysis": {
      "analyzer": {
        "hotel_analyzer": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "stop", "snowball"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "id": {"type": "long"},
      "name": {
        "type": "text",
        "analyzer": "hotel_analyzer",
        "fields": {
          "keyword": {"type": "keyword"}
        }
      },
      "address": {
        "type": "text",
        "analyzer": "hotel_analyzer"
      },
      "location": {
        "type": "geo_point"
      },
      "facilities": {"type": "keyword"},
      "price": {"type": "float"},
      "rating": {"type": "float"},
      "city": {"type": "keyword"},
      "country": {"type": "keyword"}
    }
  }
}'

echo -e "\n✅ Hotels index created"

# Destinations 인덱스 생성
curl -X PUT "localhost:9200/destinations" -H 'Content-Type: application/json' -d'
{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 0
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "fields": {
          "keyword": {"type": "keyword"}
        }
      },
      "location": {
        "type": "geo_shape"
      },
      "destinationId": {"type": "integer"},
      "type": {"type": "keyword"}
    }
  }
}'

echo -e "\n✅ Destinations index created"

# Autocomplete 인덱스 생성
curl -X PUT "localhost:9200/autocomplete" -H 'Content-Type: application/json' -d'
{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 0
  },
  "mappings": {
    "properties": {
      "name": {"type": "text"},
      "suggest": {
        "type": "completion",
        "analyzer": "standard",
        "preserve_separators": true,
        "preserve_position_increments": true,
        "max_input_length": 50
      },
      "type": {"type": "keyword"}
    }
  }
}'

echo -e "\n✅ Autocomplete index created"
echo -e "\n🎉 All indices created successfully!"
