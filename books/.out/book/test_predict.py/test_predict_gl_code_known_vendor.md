# GL code prediction: Kesko Oyj

Kesko is a Finnish retail conglomerate. With 18 invoices in the
dataset, Aito should predict GL 4400 (Supplies) with high confidence.


## Top predictions

  GL 4400    p=0.9145
  GL 6100    p=0.0285
  GL 4100    p=0.0143
  GL 4500    p=0.0131
  GL 5100    p=0.0118


## $why explanation for top prediction

```json
{
  "type": "product",
  "factors": [
    {
      "type": "baseP",
      "value": 0.14345991561181434,
      "proposition": {
        "gl_code": {
          "$has": "4400"
        }
      }
    },
    {
      "type": "product",
      "factors": [
        {
          "type": "normalizer",
          "name": "exclusiveness",
          "value": 1.0020358490248416
        },
        {
          "type": "normalizer",
          "name": "trueFalseExclusiveness",
          "value": 1.0193548387096774
        }
      ]
    },
    {
      "type": "relatedPropositionLift",
      "proposition": {
        "vendor": {
          "$has": "Kesko Oyj"
        }
      },
      "value": 6.241176470588235
    }
  ]
}
```

ok
ok
