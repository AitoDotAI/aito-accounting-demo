# $why explanation for vendor matching

The $why factors show which text tokens drove the prediction.

  Description: KESKO OYJ HELSINKI
  Predicted:   Kesko Oyj  p=0.1985


## $why factors

```json
{
  "type": "product",
  "factors": [
    {
      "type": "baseP",
      "value": 0.008333333333333333,
      "proposition": {
        "vendor_name": {
          "$has": "Kesko Oyj"
        }
      }
    },
    {
      "type": "product",
      "factors": [
        {
          "type": "normalizer",
          "name": "exclusiveness",
          "value": 1.185934205370914
        },
        {
          "type": "normalizer",
          "name": "trueFalseExclusiveness",
          "value": 0.7042293002812441
        }
      ]
    },
    {
      "type": "relatedPropositionLift",
      "proposition": {
        "$and": [
          {
            "description": {
              "$has": "kesko"
            }
          },
          {
            "description": {
              "$has": "oyj"
            }
          }
        ]
      },
      "value": 28.514603582524344
    }
  ]
}
```

The description tokens 'kesko' and 'oyj' provide strong lift
for vendor 'Kesko Oyj' via learned text associations.
