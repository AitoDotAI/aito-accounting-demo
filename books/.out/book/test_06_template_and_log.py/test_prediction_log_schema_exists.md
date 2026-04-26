# prediction_log schema


  accepted             type=Boolean    nullable=False
  confidence           type=Decimal    nullable=False
  customer_id          type=String     nullable=False
  field                type=String     nullable=False
  log_id               type=String     nullable=False
  predicted_value      type=String     nullable=True
  source               type=String     nullable=False
  timestamp            type=Int        nullable=False
  user_value           type=String     nullable=True

ok
