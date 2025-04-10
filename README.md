# NBA Games Predictor

The goal of this project was to leverage my studies in machine learning and SQL to create a web app which allows users to see predictions of upcoming NBA games from a model trained from years of NBA data.  
A huge help in creating this project was following the development of [NBA-Prediction-Modeling](https://github.com/luke-lite/NBA-Prediction-Modeling?tab=readme-ov-file#data-overview) by lule-lite

## Development
Currently working on SQL integration as the development started with pandas and csv.  
The initial model is ensemble with XGBoost and Linear Regression. Initial tests recieved an accuracy of around 60%  
Also implementing scheduled scraping so that the model can use the most recent data for the prediction of future games.
Once this is complete UI development will take place.   
I'm thinking that I will improve the model and it's features after the initial development of the app is complete.

Honestly right now the directory is a mess, but I will be cleaning before the final push of the app. Please email me for any questions on development. This is one of many personal projects I'm working on atm. 

## Data
The data was manually scraped from [[basketball-reference.com](https://www.basketball-reference.com/)].

## Modeling
NBA games have an insane number of factors which play any given night to determine a winner. As an avid watcher of the sport, I personally think injuries have play one of the hugest roles of prediction. Injury reports however are released the day of or shortly before the game. Currently adding features such as injury and player stats would be far above the capabilites of the model, so the model's predictions should be took with the HUGEST grain of salt.