"""
Sample dataset for testing fiat-lux-agents.
60 sales records with numeric correlations for regression and analytics testing.

Built-in relationships:
- amount ~ rep_experience (positive, strong)
- days_to_close ~ status (completed shortest, pending longest)
- customer_score ~ status (completed highest)
- margin_pct varies by category (Clothing highest, Food lowest)
- Electronics: high amount, low units; Food: low amount, high units
"""

SAMPLE_DATA = [
    {'id': 1, 'name': 'Alice', 'region': 'West', 'category': 'Electronics', 'status': 'pending', 'month': 'Jan', 'amount': 1732.03, 'units': 2, 'price_per_unit': 866.01, 'cost': 1168.92, 'profit': 563.11, 'margin_pct': 32.5, 'days_to_close': 26, 'rep_experience': 8, 'customer_score': 7.6},
    {'id': 2, 'name': 'Bob', 'region': 'East', 'category': 'Clothing', 'status': 'completed', 'month': 'Feb', 'amount': 685.42, 'units': 2, 'price_per_unit': 342.71, 'cost': 384.28, 'profit': 301.14, 'margin_pct': 43.9, 'days_to_close': 21, 'rep_experience': 3, 'customer_score': 6.7},
    {'id': 3, 'name': 'Carol', 'region': 'North', 'category': 'Food', 'status': 'completed', 'month': 'Mar', 'amount': 1282.78, 'units': 15, 'price_per_unit': 85.52, 'cost': 960.98, 'profit': 321.8, 'margin_pct': 25.1, 'days_to_close': 12, 'rep_experience': 12, 'customer_score': 9.7},
    {'id': 4, 'name': 'Dave', 'region': 'South', 'category': 'Office', 'status': 'cancelled', 'month': 'Apr', 'amount': 816.46, 'units': 5, 'price_per_unit': 163.29, 'cost': 516.01, 'profit': 300.45, 'margin_pct': 36.8, 'days_to_close': 58, 'rep_experience': 1, 'customer_score': 4.1},
    {'id': 5, 'name': 'Eve', 'region': 'West', 'category': 'Sports', 'status': 'completed', 'month': 'May', 'amount': 1071.44, 'units': 5, 'price_per_unit': 214.29, 'cost': 658.63, 'profit': 412.81, 'margin_pct': 38.5, 'days_to_close': 25, 'rep_experience': 9, 'customer_score': 8.6},
    {'id': 6, 'name': 'Frank', 'region': 'East', 'category': 'Electronics', 'status': 'refunded', 'month': 'Jun', 'amount': 1892.81, 'units': 3, 'price_per_unit': 630.94, 'cost': 1128.26, 'profit': 764.55, 'margin_pct': 40.4, 'days_to_close': 37, 'rep_experience': 5, 'customer_score': 2.4},
    {'id': 7, 'name': 'Grace', 'region': 'North', 'category': 'Clothing', 'status': 'completed', 'month': 'Jul', 'amount': 580.66, 'units': 4, 'price_per_unit': 145.16, 'cost': 257.83, 'profit': 322.83, 'margin_pct': 55.6, 'days_to_close': 18, 'rep_experience': 2, 'customer_score': 8.0},
    {'id': 8, 'name': 'Hank', 'region': 'South', 'category': 'Food', 'status': 'cancelled', 'month': 'Aug', 'amount': 876.77, 'units': 18, 'price_per_unit': 48.71, 'cost': 616.96, 'profit': 259.81, 'margin_pct': 29.6, 'days_to_close': 41, 'rep_experience': 11, 'customer_score': 3.8},
    {'id': 9, 'name': 'Ivy', 'region': 'West', 'category': 'Office', 'status': 'pending', 'month': 'Sep', 'amount': 1263.31, 'units': 8, 'price_per_unit': 157.91, 'cost': 747.5, 'profit': 515.81, 'margin_pct': 40.8, 'days_to_close': 86, 'rep_experience': 7, 'customer_score': 7.3},
    {'id': 10, 'name': 'Jack', 'region': 'East', 'category': 'Sports', 'status': 'pending', 'month': 'Oct', 'amount': 898.01, 'units': 1, 'price_per_unit': 898.01, 'cost': 645.46, 'profit': 252.55, 'margin_pct': 28.1, 'days_to_close': 23, 'rep_experience': 4, 'customer_score': 6.1},
    {'id': 11, 'name': 'Karen', 'region': 'North', 'category': 'Electronics', 'status': 'completed', 'month': 'Nov', 'amount': 2241.67, 'units': 3, 'price_per_unit': 747.22, 'cost': 1483.37, 'profit': 758.3, 'margin_pct': 33.8, 'days_to_close': 20, 'rep_experience': 6, 'customer_score': 9.5},
    {'id': 12, 'name': 'Leo', 'region': 'South', 'category': 'Clothing', 'status': 'pending', 'month': 'Dec', 'amount': 1338.59, 'units': 12, 'price_per_unit': 111.55, 'cost': 667.89, 'profit': 670.7, 'margin_pct': 50.1, 'days_to_close': 35, 'rep_experience': 14, 'customer_score': 7.5},
    {'id': 13, 'name': 'Mia', 'region': 'West', 'category': 'Food', 'status': 'cancelled', 'month': 'Jan', 'amount': 928.36, 'units': 9, 'price_per_unit': 103.15, 'cost': 685.39, 'profit': 242.97, 'margin_pct': 26.2, 'days_to_close': 15, 'rep_experience': 10, 'customer_score': 3.6},
    {'id': 14, 'name': 'Ned', 'region': 'East', 'category': 'Office', 'status': 'completed', 'month': 'Feb', 'amount': 1187.46, 'units': 7, 'price_per_unit': 169.64, 'cost': 656.25, 'profit': 531.21, 'margin_pct': 44.7, 'days_to_close': 18, 'rep_experience': 3, 'customer_score': 8.4},
    {'id': 15, 'name': 'Olivia', 'region': 'North', 'category': 'Sports', 'status': 'completed', 'month': 'Mar', 'amount': 1005.04, 'units': 1, 'price_per_unit': 1005.04, 'cost': 640.76, 'profit': 364.28, 'margin_pct': 36.2, 'days_to_close': 9, 'rep_experience': 8, 'customer_score': 9.6},
    {'id': 16, 'name': 'Paul', 'region': 'South', 'category': 'Electronics', 'status': 'cancelled', 'month': 'Apr', 'amount': 1433.02, 'units': 3, 'price_per_unit': 477.67, 'cost': 890.97, 'profit': 542.05, 'margin_pct': 37.8, 'days_to_close': 35, 'rep_experience': 1, 'customer_score': 5.9},
    {'id': 17, 'name': 'Quinn', 'region': 'West', 'category': 'Clothing', 'status': 'cancelled', 'month': 'May', 'amount': 1064.1, 'units': 3, 'price_per_unit': 354.7, 'cost': 541.22, 'profit': 522.88, 'margin_pct': 49.1, 'days_to_close': 17, 'rep_experience': 7, 'customer_score': 5.2},
    {'id': 18, 'name': 'Rosa', 'region': 'East', 'category': 'Food', 'status': 'cancelled', 'month': 'Jun', 'amount': 1234.46, 'units': 24, 'price_per_unit': 51.44, 'cost': 855.17, 'profit': 379.29, 'margin_pct': 30.7, 'days_to_close': 34, 'rep_experience': 13, 'customer_score': 6.0},
    {'id': 19, 'name': 'Sam', 'region': 'North', 'category': 'Office', 'status': 'completed', 'month': 'Jul', 'amount': 983.53, 'units': 1, 'price_per_unit': 983.53, 'cost': 629.33, 'profit': 354.2, 'margin_pct': 36.0, 'days_to_close': 17, 'rep_experience': 5, 'customer_score': 9.7},
    {'id': 20, 'name': 'Tina', 'region': 'South', 'category': 'Sports', 'status': 'cancelled', 'month': 'Aug', 'amount': 512.04, 'units': 2, 'price_per_unit': 256.02, 'cost': 381.26, 'profit': 130.78, 'margin_pct': 25.5, 'days_to_close': 36, 'rep_experience': 2, 'customer_score': 3.3},
    {'id': 21, 'name': 'Alice', 'region': 'West', 'category': 'Electronics', 'status': 'cancelled', 'month': 'Sep', 'amount': 1934.82, 'units': 4, 'price_per_unit': 483.7, 'cost': 1024.62, 'profit': 910.2, 'margin_pct': 47.0, 'days_to_close': 19, 'rep_experience': 8, 'customer_score': 5.0},
    {'id': 22, 'name': 'Bob', 'region': 'East', 'category': 'Clothing', 'status': 'pending', 'month': 'Oct', 'amount': 1043.16, 'units': 12, 'price_per_unit': 86.93, 'cost': 496.36, 'profit': 546.8, 'margin_pct': 52.4, 'days_to_close': 69, 'rep_experience': 3, 'customer_score': 6.3},
    {'id': 23, 'name': 'Carol', 'region': 'North', 'category': 'Food', 'status': 'pending', 'month': 'Nov', 'amount': 1138.62, 'units': 29, 'price_per_unit': 39.26, 'cost': 920.25, 'profit': 218.37, 'margin_pct': 19.2, 'days_to_close': 33, 'rep_experience': 12, 'customer_score': 6.6},
    {'id': 24, 'name': 'Dave', 'region': 'South', 'category': 'Office', 'status': 'pending', 'month': 'Dec', 'amount': 729.25, 'units': 2, 'price_per_unit': 364.62, 'cost': 388.39, 'profit': 340.86, 'margin_pct': 46.7, 'days_to_close': 26, 'rep_experience': 1, 'customer_score': 5.3},
    {'id': 25, 'name': 'Eve', 'region': 'West', 'category': 'Sports', 'status': 'completed', 'month': 'Jan', 'amount': 1103.13, 'units': 5, 'price_per_unit': 220.63, 'cost': 705.54, 'profit': 397.59, 'margin_pct': 36.0, 'days_to_close': 11, 'rep_experience': 9, 'customer_score': 7.3},
    {'id': 26, 'name': 'Frank', 'region': 'East', 'category': 'Electronics', 'status': 'refunded', 'month': 'Feb', 'amount': 1879.08, 'units': 4, 'price_per_unit': 469.77, 'cost': 1042.23, 'profit': 836.85, 'margin_pct': 44.5, 'days_to_close': 18, 'rep_experience': 5, 'customer_score': 2.5},
    {'id': 27, 'name': 'Grace', 'region': 'North', 'category': 'Clothing', 'status': 'completed', 'month': 'Mar', 'amount': 723.21, 'units': 12, 'price_per_unit': 60.27, 'cost': 426.87, 'profit': 296.34, 'margin_pct': 41.0, 'days_to_close': 26, 'rep_experience': 2, 'customer_score': 8.5},
    {'id': 28, 'name': 'Hank', 'region': 'South', 'category': 'Food', 'status': 'completed', 'month': 'Apr', 'amount': 1267.03, 'units': 7, 'price_per_unit': 181.0, 'cost': 994.92, 'profit': 272.11, 'margin_pct': 21.5, 'days_to_close': 10, 'rep_experience': 11, 'customer_score': 8.4},
    {'id': 29, 'name': 'Ivy', 'region': 'West', 'category': 'Office', 'status': 'completed', 'month': 'May', 'amount': 1167.15, 'units': 15, 'price_per_unit': 77.81, 'cost': 754.48, 'profit': 412.67, 'margin_pct': 35.4, 'days_to_close': 28, 'rep_experience': 7, 'customer_score': 9.4},
    {'id': 30, 'name': 'Jack', 'region': 'East', 'category': 'Sports', 'status': 'completed', 'month': 'Jun', 'amount': 814.7, 'units': 1, 'price_per_unit': 814.7, 'cost': 477.07, 'profit': 337.63, 'margin_pct': 41.4, 'days_to_close': 32, 'rep_experience': 4, 'customer_score': 9.2},
    {'id': 31, 'name': 'Karen', 'region': 'North', 'category': 'Electronics', 'status': 'completed', 'month': 'Jul', 'amount': 1719.81, 'units': 4, 'price_per_unit': 429.95, 'cost': 924.5, 'profit': 795.31, 'margin_pct': 46.2, 'days_to_close': 11, 'rep_experience': 6, 'customer_score': 6.8},
    {'id': 32, 'name': 'Leo', 'region': 'South', 'category': 'Clothing', 'status': 'completed', 'month': 'Aug', 'amount': 2155.01, 'units': 5, 'price_per_unit': 431.0, 'cost': 1128.92, 'profit': 1026.09, 'margin_pct': 47.6, 'days_to_close': 29, 'rep_experience': 14, 'customer_score': 10.0},
    {'id': 33, 'name': 'Mia', 'region': 'West', 'category': 'Food', 'status': 'pending', 'month': 'Sep', 'amount': 1096.84, 'units': 19, 'price_per_unit': 57.73, 'cost': 867.4, 'profit': 229.44, 'margin_pct': 20.9, 'days_to_close': 22, 'rep_experience': 10, 'customer_score': 7.7},
    {'id': 34, 'name': 'Ned', 'region': 'East', 'category': 'Office', 'status': 'completed', 'month': 'Oct', 'amount': 801.81, 'units': 8, 'price_per_unit': 100.23, 'cost': 456.62, 'profit': 345.19, 'margin_pct': 43.1, 'days_to_close': 31, 'rep_experience': 3, 'customer_score': 7.1},
    {'id': 35, 'name': 'Olivia', 'region': 'North', 'category': 'Sports', 'status': 'refunded', 'month': 'Nov', 'amount': 837.08, 'units': 2, 'price_per_unit': 418.54, 'cost': 534.44, 'profit': 302.64, 'margin_pct': 36.2, 'days_to_close': 18, 'rep_experience': 8, 'customer_score': 2.8},
    {'id': 36, 'name': 'Paul', 'region': 'South', 'category': 'Electronics', 'status': 'cancelled', 'month': 'Dec', 'amount': 1617.94, 'units': 1, 'price_per_unit': 1617.94, 'cost': 1010.47, 'profit': 607.47, 'margin_pct': 37.5, 'days_to_close': 41, 'rep_experience': 1, 'customer_score': 4.6},
    {'id': 37, 'name': 'Quinn', 'region': 'West', 'category': 'Clothing', 'status': 'refunded', 'month': 'Jan', 'amount': 1112.48, 'units': 4, 'price_per_unit': 278.12, 'cost': 614.3, 'profit': 498.18, 'margin_pct': 44.8, 'days_to_close': 15, 'rep_experience': 7, 'customer_score': 4.3},
    {'id': 38, 'name': 'Rosa', 'region': 'East', 'category': 'Food', 'status': 'completed', 'month': 'Feb', 'amount': 1615.31, 'units': 1, 'price_per_unit': 1615.31, 'cost': 1207.46, 'profit': 407.85, 'margin_pct': 25.2, 'days_to_close': 31, 'rep_experience': 13, 'customer_score': 10.0},
    {'id': 39, 'name': 'Sam', 'region': 'North', 'category': 'Office', 'status': 'completed', 'month': 'Mar', 'amount': 1015.46, 'units': 15, 'price_per_unit': 67.7, 'cost': 606.41, 'profit': 409.05, 'margin_pct': 40.3, 'days_to_close': 9, 'rep_experience': 5, 'customer_score': 7.5},
    {'id': 40, 'name': 'Tina', 'region': 'South', 'category': 'Sports', 'status': 'completed', 'month': 'Apr', 'amount': 610.09, 'units': 5, 'price_per_unit': 122.02, 'cost': 396.5, 'profit': 213.59, 'margin_pct': 35.0, 'days_to_close': 35, 'rep_experience': 2, 'customer_score': 8.6},
    {'id': 41, 'name': 'Alice', 'region': 'West', 'category': 'Electronics', 'status': 'completed', 'month': 'May', 'amount': 2101.0, 'units': 1, 'price_per_unit': 2101.0, 'cost': 1115.62, 'profit': 985.38, 'margin_pct': 46.9, 'days_to_close': 9, 'rep_experience': 8, 'customer_score': 7.2},
    {'id': 42, 'name': 'Bob', 'region': 'East', 'category': 'Clothing', 'status': 'completed', 'month': 'Jun', 'amount': 758.66, 'units': 10, 'price_per_unit': 75.87, 'cost': 426.43, 'profit': 332.23, 'margin_pct': 43.8, 'days_to_close': 17, 'rep_experience': 3, 'customer_score': 8.7},
    {'id': 43, 'name': 'Carol', 'region': 'North', 'category': 'Food', 'status': 'cancelled', 'month': 'Jul', 'amount': 1155.69, 'units': 4, 'price_per_unit': 288.92, 'cost': 940.02, 'profit': 215.67, 'margin_pct': 18.7, 'days_to_close': 29, 'rep_experience': 12, 'customer_score': 4.4},
    {'id': 44, 'name': 'Dave', 'region': 'South', 'category': 'Office', 'status': 'completed', 'month': 'Aug', 'amount': 946.61, 'units': 5, 'price_per_unit': 189.32, 'cost': 597.23, 'profit': 349.38, 'margin_pct': 36.9, 'days_to_close': 21, 'rep_experience': 1, 'customer_score': 8.7},
    {'id': 45, 'name': 'Eve', 'region': 'West', 'category': 'Sports', 'status': 'pending', 'month': 'Sep', 'amount': 1103.53, 'units': 3, 'price_per_unit': 367.84, 'cost': 730.31, 'profit': 373.22, 'margin_pct': 33.8, 'days_to_close': 75, 'rep_experience': 9, 'customer_score': 7.2},
    {'id': 46, 'name': 'Frank', 'region': 'East', 'category': 'Electronics', 'status': 'completed', 'month': 'Oct', 'amount': 1618.98, 'units': 1, 'price_per_unit': 1618.98, 'cost': 871.32, 'profit': 747.66, 'margin_pct': 46.2, 'days_to_close': 13, 'rep_experience': 5, 'customer_score': 7.5},
    {'id': 47, 'name': 'Grace', 'region': 'North', 'category': 'Clothing', 'status': 'completed', 'month': 'Nov', 'amount': 900.08, 'units': 7, 'price_per_unit': 128.58, 'cost': 382.27, 'profit': 517.81, 'margin_pct': 57.5, 'days_to_close': 28, 'rep_experience': 2, 'customer_score': 9.4},
    {'id': 48, 'name': 'Hank', 'region': 'South', 'category': 'Food', 'status': 'completed', 'month': 'Dec', 'amount': 924.7, 'units': 12, 'price_per_unit': 77.06, 'cost': 620.79, 'profit': 303.91, 'margin_pct': 32.9, 'days_to_close': 5, 'rep_experience': 11, 'customer_score': 9.3},
    {'id': 49, 'name': 'Ivy', 'region': 'West', 'category': 'Office', 'status': 'completed', 'month': 'Jan', 'amount': 1666.87, 'units': 14, 'price_per_unit': 119.06, 'cost': 879.59, 'profit': 787.28, 'margin_pct': 47.2, 'days_to_close': 13, 'rep_experience': 7, 'customer_score': 7.3},
    {'id': 50, 'name': 'Jack', 'region': 'East', 'category': 'Sports', 'status': 'pending', 'month': 'Feb', 'amount': 628.92, 'units': 8, 'price_per_unit': 78.61, 'cost': 452.8, 'profit': 176.12, 'margin_pct': 28.0, 'days_to_close': 76, 'rep_experience': 4, 'customer_score': 6.6},
    {'id': 51, 'name': 'Karen', 'region': 'North', 'category': 'Electronics', 'status': 'completed', 'month': 'Mar', 'amount': 1833.64, 'units': 1, 'price_per_unit': 1833.64, 'cost': 1065.7, 'profit': 767.94, 'margin_pct': 41.9, 'days_to_close': 17, 'rep_experience': 6, 'customer_score': 7.6},
    {'id': 52, 'name': 'Leo', 'region': 'South', 'category': 'Clothing', 'status': 'completed', 'month': 'Apr', 'amount': 1893.84, 'units': 9, 'price_per_unit': 210.43, 'cost': 1000.06, 'profit': 893.78, 'margin_pct': 47.2, 'days_to_close': 30, 'rep_experience': 14, 'customer_score': 8.8},
    {'id': 53, 'name': 'Mia', 'region': 'West', 'category': 'Food', 'status': 'refunded', 'month': 'May', 'amount': 853.24, 'units': 12, 'price_per_unit': 71.1, 'cost': 619.02, 'profit': 234.22, 'margin_pct': 27.5, 'days_to_close': 45, 'rep_experience': 10, 'customer_score': 2.6},
    {'id': 54, 'name': 'Ned', 'region': 'East', 'category': 'Office', 'status': 'pending', 'month': 'Jun', 'amount': 1138.43, 'units': 7, 'price_per_unit': 162.63, 'cost': 627.14, 'profit': 511.29, 'margin_pct': 44.9, 'days_to_close': 56, 'rep_experience': 3, 'customer_score': 6.3},
    {'id': 55, 'name': 'Olivia', 'region': 'North', 'category': 'Sports', 'status': 'pending', 'month': 'Jul', 'amount': 1045.69, 'units': 1, 'price_per_unit': 1045.69, 'cost': 696.86, 'profit': 348.83, 'margin_pct': 33.4, 'days_to_close': 74, 'rep_experience': 8, 'customer_score': 7.5},
    {'id': 56, 'name': 'Paul', 'region': 'South', 'category': 'Electronics', 'status': 'refunded', 'month': 'Aug', 'amount': 1311.05, 'units': 4, 'price_per_unit': 327.76, 'cost': 901.22, 'profit': 409.83, 'margin_pct': 31.3, 'days_to_close': 37, 'rep_experience': 1, 'customer_score': 3.0},
    {'id': 57, 'name': 'Quinn', 'region': 'West', 'category': 'Clothing', 'status': 'completed', 'month': 'Sep', 'amount': 1361.5, 'units': 5, 'price_per_unit': 272.3, 'cost': 692.62, 'profit': 668.88, 'margin_pct': 49.1, 'days_to_close': 24, 'rep_experience': 7, 'customer_score': 7.8},
    {'id': 58, 'name': 'Rosa', 'region': 'East', 'category': 'Food', 'status': 'pending', 'month': 'Oct', 'amount': 1267.12, 'units': 25, 'price_per_unit': 50.68, 'cost': 897.23, 'profit': 369.89, 'margin_pct': 29.2, 'days_to_close': 78, 'rep_experience': 13, 'customer_score': 7.5},
    {'id': 59, 'name': 'Sam', 'region': 'North', 'category': 'Office', 'status': 'completed', 'month': 'Nov', 'amount': 988.37, 'units': 5, 'price_per_unit': 197.67, 'cost': 614.93, 'profit': 373.44, 'margin_pct': 37.8, 'days_to_close': 28, 'rep_experience': 5, 'customer_score': 8.6},
    {'id': 60, 'name': 'Tina', 'region': 'South', 'category': 'Sports', 'status': 'completed', 'month': 'Dec', 'amount': 643.85, 'units': 8, 'price_per_unit': 80.48, 'cost': 397.34, 'profit': 246.51, 'margin_pct': 38.3, 'days_to_close': 34, 'rep_experience': 2, 'customer_score': 8.8},
]

SCHEMA = """Columns:
- id (int): unique row identifier
- name (str): salesperson name (20 reps)
- region (str): West | East | North | South
- category (str): Electronics | Clothing | Food | Office | Sports
- status (str): completed | pending | cancelled | refunded
- month (str): Jan through Dec
- amount (float): sale amount in dollars
- units (int): number of units sold
- price_per_unit (float): amount / units
- cost (float): cost of goods sold
- profit (float): amount - cost
- margin_pct (float): profit as % of amount (0-100)
- days_to_close (int): length of sales cycle in days
- rep_experience (int): years of experience of salesperson (1-14)
- customer_score (float): customer satisfaction score (1.0-10.0)
"""

SUMMARY = {
    "total_rows": 60,
    "columns": ["id", "name", "region", "category", "status", "month",
                "amount", "units", "price_per_unit", "cost", "profit",
                "margin_pct", "days_to_close", "rep_experience", "customer_score"],
    "categories": ["Electronics", "Clothing", "Food", "Office", "Sports"],
    "regions": ["West", "East", "North", "South"],
    "statuses": ["completed", "pending", "cancelled", "refunded"],
    "amount_range": [512.04, 2241.67],
}
