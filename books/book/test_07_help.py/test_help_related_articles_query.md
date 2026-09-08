# _recommend: users who read this also read



## Query

```json
{
  "from": "help_impressions",
  "basedOn": [],
  "where": {
    "prev_article_id.article_id": "LEGAL-00",
    "customer_id": "CUST-0000",
    "article_id.customer_id": {
      "$or": [
        "*",
        "CUST-0000"
      ]
    }
  },
  "recommend": "article_id",
  "goal": {
    "clicked": true
  },
  "select": [
    "$p",
    "article_id",
    "title",
    "category",
    "customer_id"
  ],
  "limit": 5
}
```


## Top 4 candidates

  p=0.462  [internal] [own-internal  ] Cost centre rules at Tornio Retail Oy Ab
  p=0.433  [internal] [own-internal  ] Quarter-end close at Tornio Retail Oy Ab
  p=0.417  [internal] [own-internal  ] Override policy at Tornio Retail Oy Ab
  p=0.315  [app     ] [global        ] Form Fill: confirming vs overriding predictions

ok
ok
