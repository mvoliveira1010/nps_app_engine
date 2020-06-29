from flask import Flask, render_template, request, send_file, flash, redirect
from google.cloud import storage
from werkzeug.utils import secure_filename
from datetime import datetime,date,timedelta
from calendar import monthrange
import os, gcsfs, time, pytz, requests, json, pandas as pd

ALLOWED_EXTENSIONS = {'csv'}

app = Flask(__name__)
app.secret_key = "configuração necessária para apresentar mensagens de erro"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
	
def upload_to_storage(file):
	storage_client = storage.Client()
	bucket = storage_client.get_bucket('disparo_nps_corporativos')
	blob = bucket.blob(file.filename)
	blob.upload_from_string(file.read(), content_type=file.content_type)

def verify_schedule(date,max_date):
	message = None
	result = None
	min_date = datetime.today()+timedelta(hours=1)
	try:
		formated_date = datetime.strptime(date, "%Y-%m-%dT%H:%M")
		if  formated_date > min_date and formated_date < max_date:
			message = formated_date
			result = True
		else:
			message = 'Alguma das datas é menor ou maior que o período permitido.'
			result = False
	except Exception as erro:
		message = 'Insira datas válidas.'
		result = False
	return result,message

def create_dispatch(customers,timestamp,max_date):
	dispatch = {"customers":[],
                "schedule_time":timestamp,
                "finish_time":int(max_date.timestamp())}
	for index, row in customers.iterrows():
		customer = {"name":row['nome_completo'],
			"email":row['email'],
			"phone":row['telefone'],
			"tags" : []}
		for k,v in row.items():
			if k not in ['nome_completo','email','telefone']:
				if isinstance(v, date):
					v = v.strftime("%Y-%m-%d")
				customer['tags'].append({"name":k,"value":v})
		dispatch['customers'].append(customer)
	return dispatch

def send_dispatch(campaign_code,dispatch):
	token = "1f6052edf29803f68a4a0ff729f4182a"
	url = f"https://api.tracksale.co/v2/campaign/{campaign_code}/dispatch"
	headers = {
		'content-type': "application/json",
		'authorization': f"bearer {token}",
		'cache-control': "no-cache"
	}
	response = requests.request("POST", url, data=json.dumps(dispatch), headers=headers)
	
def load_dispatch(customers,datas_json,max_date):
	try:
		limit = round(len(customers)/5)+1
		i = 1
		while len(customers)>0:
			df_aux = customers.iloc[:limit]
			dispatch = create_dispatch(df_aux,datas_json[f'dia{i}'],max_date)
			send_dispatch(46,dispatch)
			customers = customers[limit:]
			i+=1
		return True,'Seus disparos foram agendados com sucesso!'
	except Exception as erro:
		return False,'Insira uma base com formato correto (confira na documentação).'

@app.route('/')
def upload():
    return render_template('upload.html')
		   
@app.route('/upload_arquivo', methods=['POST','GET'])
def upload_arquivo():
	if request.method == 'POST':
		datas_json = dict()
		
		file = request.files['inputFile']
		if file and allowed_file(file.filename):
			tz = pytz.timezone('America/Sao_Paulo')
			now = datetime.now(tz)
			max_date_str = f"{now.year}-{now.month}-{monthrange(now.year,now.month)[1]} 23:59"
			max_date = datetime.strptime(f"{max_date_str}","%Y-%m-%d %H:%M")
			#VALIDANDO AS DATAS
			result,message = True,None
			for i in range(1,5+1):
				validacao = verify_schedule(request.form[f'dia{i}'],max_date)
				if validacao[0] is False:
					result,message = validacao[0],validacao[1]
				else:
					datas_json.update({f'dia{i}':int(validacao[1].timestamp())})
					
			if result is False:
				flash(message,'error')
				return render_template('upload.html')
			else:
				upload_to_storage(request.files.get('inputFile'))
				df = pd.read_csv(f'gs://disparo_nps_corporativos/{file.filename}')
				customers = df.where(pd.notnull(df), None)
				result = load_dispatch(customers,datas_json,max_date)
				if result[0] is False:
					flash(result[1],'error')
					return render_template('upload.html')
			flash(result[1])
			return render_template('upload_realizado.html')
		else:
			flash('Insira um arquivo no formato ".csv".','error')
			return render_template('upload.html')
	else:
		return redirect('/')
if __name__ == "__main__":
    app.run(debug=True)
