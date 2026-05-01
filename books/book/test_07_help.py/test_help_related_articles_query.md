# _recommend: users who read this also read



## Query

```json
{
  "from": "help_impressions",
  "basedOn": [
    {
      "article_id": "LEGAL-00"
    },
    {
      "customer_id": "CUST-0000"
    }
  ],
  "where": {
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

  p=0.352  [internal] [own-internal  ] Cost centre rules at Tornio Retail Oy Ab
  p=0.350  [internal] [own-internal  ] Quarter-end close at Tornio Retail Oy Ab
  p=0.332  [internal] [own-internal  ] Approval policy: invoices over €10,000
  p=0.319  [internal] [own-internal  ] Override policy at Tornio Retail Oy Ab

ok
ok
