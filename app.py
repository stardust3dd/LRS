# Flask imports
from flask import Flask, render_template, session, redirect, url_for, flash
from flask_wtf import FlaskForm
from wtforms import FloatField, StringField, SelectField, SubmitField
from wtforms.validators import DataRequired
# LRS imports
import re
from imdb import IMDb
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
from itertools import permutations, combinations

app= Flask(__name__)
app.config['SECRET_KEY']= 'mykey'

class movinput(FlaskForm):
    url1= StringField('movie #1: ', validators= [DataRequired()])
    rat1= FloatField(validators= [DataRequired()])
    url2= StringField('movie #2: ', validators= [DataRequired()])
    rat2= FloatField(validators= [DataRequired()])
    url3= StringField('movie #3: ', validators= [DataRequired()])
    rat3= FloatField(validators= [DataRequired()])
    lang= SelectField(choices= [('en', 'English'), ('hi', 'Hindi')])
    submit= SubmitField('submit!')

def getmovies():
    ia= IMDb()
    tmp= []
    urls= [session['url1'], session['url2'], session['url3']]
    rats= [session['rat1'], session['rat2'], session['rat3']]
    for i in range(0, 3):
        mvid= re.search('title/tt(.+?)/', urls[i])
        if mvid:
            mvid= ia.get_movie(mvid.group(1))
            deets= ['title','year','genres','rating','votes','directors','cast','cover url']
            movie= {deet:mvid[deet] for deet in deets}       
            cast= [str(i).replace(' ','') for i in movie['cast']]    
            movie['cast']= cast[0:4] # consider only the top 4 billed cast members
            dirs= [str(i).replace(' ','') for i in movie['directors']]
            movie['directors']= dirs
            name= movie['title']
            movie['score']= float(rats[i])
            tmp.append(movie)  
    return tmp  

def getuser(movies):
    #user movies dataframe
    user= pd.DataFrame(movies)
    user['directors']= user['directors'].replace(' ', '')
    user['cast']= user['cast'].replace(' ', '')
    lang= session['lang']
    user['year']= user['year'].astype(str)
    user['year']= '('+user['year']+')'
    #user profile creation
    user_genres= set([i for j in user['genres'].tolist() for i in j])
    user_genre_combinations=[]
    for i in range(len(user_genres)):
        oc = combinations(user_genres, i + 1)
        for c in oc:
            user_genre_combinations.append(','.join(list(c)).lower())
    # scraped movies dataframe creation
    scraped_movies=[]
    scraped_imgs= []
    for genre in user_genre_combinations:   
        url= 'https://www.imdb.com/search/title/?title_type=feature,tv_movie&genres='+genre+'&languages='+lang+'&sort=num_votes,desc'
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser') 
        rat= soup.find_all('div',{'class':'lister-item-content'})  
        imgs= soup.find_all('div',{'class':'lister-item-image float-left'})
        for i, j in zip(rat, imgs):
            for nmyr, gnr, rt, crew, vt, img_url in zip(i.find_all('h3',{'class':'lister-item-header'}),i.find_all('p', {'class':'text-muted'}),i.find_all('div', {'class': 'ratings-bar'}),i.find_all('p', {'class': ''}),i.find_all('p', {'class': 'sort-num_votes-visible'}),j.find_all('img', {'class': 'loadlate'})):
                movie= {}
                movie['title']= nmyr.find('a').text
                movie['year']= nmyr.find('span', {'class': 'lister-item-year text-muted unbold'}).text
                movie['genres']= gnr.find('span', {'class': 'genre'}).text.replace('\n', '').replace(' ', '').split(',')
                movie['rating']= rt.find('strong').text
                movie['votes']= vt.find('span', {'name': 'nv'}).text
                dirr= crew.text.replace('\n', '').replace(' ', '').split('|')[0]        
                cast= crew.text.replace('\n', '').replace(' ', '').split('|')[1]
                movie['directors']= dirr.split(':')[1].split(',')
                movie['cast']= cast.split(':')[1].split(',')
                img_url= re.search('loadlate="(.+?)" src', str(img_url))
                movie['cover url']= img_url.group(1)
                scraped_movies.append(movie)
    dataset= pd.DataFrame(scraped_movies)
    dataset.drop_duplicates(['cover url','votes'], keep= 'first', inplace= True)
    # concatenate user_movies & scraped_movies to create final dataset; fill all missing values with 0
    data= pd.concat([dataset, user.drop(['score'], axis= 1)]).reset_index(drop= True)
    for i, r in data.iterrows():
        for genre in r['genres']:
            data.at[i, genre] = 1
        for actor in r['cast']:
            data.at[i, actor] = 1
        for dirr in r['directors']:
            data.at[i, dirr] = 1
    data= data.fillna(0)
    # user profile creation
    userprof= data[-3:].drop(['title','year','genres','rating','votes','directors','cast','cover url'], axis= 1).reset_index(drop= True)
    userprof= userprof.transpose().dot(user['score'])
    # recommendation rankings dataframe creation
    rec= ((data.drop(['title','year','genres','rating','votes','directors','cast','cover url'], axis= 1)*userprof).sum(axis=1))/(userprof.sum())
    rec= pd.DataFrame(rec, columns= ['RS'])
    # user movies should come at the very top, that's how we check if the recommendations are working
    rec= pd.concat([dataset.reset_index(drop= True), rec[:-3].reset_index(drop= True)], axis= 1)
    rec.sort_values(['RS'], ascending= False, inplace= True, ignore_index= True)
    rec= pd.concat([rec.reset_index(drop= True), user.reset_index(drop= True)]).drop_duplicates(['title'], keep= False)
    rec= rec.reset_index(drop= True)
    rec.drop(['score'], inplace= True, axis= 1)
    rec= rec.to_dict('records')
    return user, rec

@app.route('/', methods=['GET', 'POST'])
def home():
    form= movinput()
    if form.validate_on_submit():
        session['url1']= form.url1.data
        session['url2']= form.url2.data
        session['url3']= form.url3.data
        session['rat1']= form.rat1.data
        session['rat2']= form.rat2.data
        session['rat3']= form.rat3.data
        session['lang']= form.lang.data
        print('validated on submission')
        return redirect(url_for('recommendations'))
    else:
        print('ble')
        
    return render_template('index.html', form= form)

@app.route('/recommendations')
def recommendations():
    form= movinput()
    movies= getmovies()
    user, rec= getuser(movies)    
    return render_template('rec.html', form= form, movies= movies, user= user, rec= rec, num= len(rec))

if __name__ == "__main__":
    app.run(debug= True)