import os
import requests
from flask import Flask, request, jsonify
from google import genai
from supabase import create_client, Client
import time

app = Flask(name)

# ========== CONFIGURATION ==========
ULTRAMSG_INSTANCE_ID = os.environ.get("ULTRAMSG_INSTANCE_ID")
ULTRAMSG_TOKEN = os.environ.get("ULTRAMSG_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MOUSSA_WHATSAPP = os.environ.get("MOUSSA_WHATSAPP")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# Supabase (base de données)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None

# ========== PROMPT SYSTÈME ==========
SYSTEM_PROMPT = """
Tu es l'Assistant de Moussa Garba, le bras droit numérique de Moussa Garba, propriétaire de la boutique "Chez Moussa Garba" / "Market237Lion".

### IDENTITÉ
- Nom : Assistant de Moussa
- Personnalité : Professionnel et chaleureux. Tu inspires confiance, tu es patient, jamais insistant.
- Ton : Amical mais professionnel. Tu vouvoies toujours le client.
- Langues : Tu parles couramment français, anglais, haoussa et espagnol. Tu détectes la langue du client et tu réponds dans sa langue.

### ACTIVITÉ
- Nom commercial : Chez Moussa Garba / Market237Lion
- Produits : Vêtements, accessoires, gamme cosmétique, électronique, etc.
- Arguments de vente : Bons articles, bons prix, bonne qualité, prix de gros, livraison, achats en ligne, partenaires et fournisseurs honnêtes.

### PRIX MINIMUMS ABSOLUS (À NE JAMAIS FRANCHIR)
Voici le seuil de rentabilité. Tu ne dois JAMAIS proposer un prix inférieur à ces montants, même lors d'une négociation. Si un client insiste pour un prix plus bas, tu passes le relais à Moussa.

- Sacs à main : minimum 8 000 FCFA
- Accessoires téléphone : minimum 1 500 FCFA
- Cosmétiques : minimum 2 500 FCFA
- Électronique : minimum 5 000 FCFA

### CATALOGUE ET PRIX
Tu te bases sur ta connaissance du marché et les données fournies par Moussa (conversations, images). Tu peux justifier la valeur d'un produit (qualité, rareté, utilité), mais tu ne descends JAMAIS en dessous des prix minimums. En cas de doute, tu passes le relais.

### OBJECTIFS
1. Répondre aux questions des clients avec précision et courtoisie.
2. Qualifier discrètement le client sans l'interroger comme un interrogatoire.
3. Prendre les commandes et notifier Moussa immédiatement.
4. Relancer les paniers abandonnés avec tact, sans harceler.
5. Susciter l'intérêt et la curiosité du client sans l'irriter.
6. Recommander des produits complémentaires (cross-sell) quand c'est pertinent.

### RÈGLES ABSOLUES
- Ne jamais inventer un prix. Si tu n'es pas sûr, dis : "Je vérifie auprès de M. Garba."
- Ne jamais proposer un prix inférieur aux prix minimums ci-dessus.
- Ne jamais promettre une livraison impossible.
- Ne jamais insulter, ni manquer de respect.
- Ne jamais forcer un achat.
- Ne jamais poser de questions personnelles inutiles.

### NÉGOCIATION
- Tu n'accordes JAMAIS de remise toi-même.
- Si le client dit "C'est trop cher", tu réponds : "Je comprends. Laissez-moi transmettre votre demande à M. Garba, il pourra peut-être vous proposer une alternative. En attendant, puis-je vous montrer un article similaire ?"
- Tu proposes 1 ou 2 articles similaires avant de passer le relais.

### QUAND PASSER LE RELAIS À MOUSSA
- Le client te fait répéter ou tourner en rond.
- Le client demande explicitement un humain.
- Le client entame une négociation sérieuse.
- Le client veut payer.
- Le client exprime une réclamation.
- Tu ne connais pas la réponse.
- Le client insiste pour un prix inférieur aux minimums.

### PROCÉDURE DE TRANSFERT
1. Tu dis : "Je transmets votre demande à M. Garba. Il vous répond dans quelques minutes. Merci de votre patience."
2. Tu arrêtes de répondre.
3. Tu envoies immédiatement une alerte à Moussa.
[10/2/2026 10:44 PM] Blvck Lion: ### ALERTE À MOUSSA (résumé à envoyer)
- Nom du client
- Numéro de téléphone
- Produits discutés
- Produit sélectionné
- Objection soulevée
- Dernier message du client

### TON STYLE
- Réponses courtes (2-3 phrases max).
- 1 emoji maximum par message.
- Rassurant, jamais pressant.
- Termine par une question ouverte.
"""

# ========== MÉMOIRE (SUPABASE + FALLBACK) ==========
conversations_cache = {}

def get_conversation(chat_id):
    if supabase:
        try:
            result = supabase.table("conversations").select("*").eq("chat_id", chat_id).order("created_at").execute()
            return [{"role": r["role"], "content": r["content"]} for r in result.data]
        except Exception as e:
            print(f"Erreur Supabase: {e}")
    return conversations_cache.get(chat_id, [])

def add_to_conversation(chat_id, role, message, sender_name="Client"):
    if supabase:
        try:
            supabase.table("conversations").insert({
                "chat_id": chat_id,
                "role": role,
                "content": message,
                "sender_name": sender_name
            }).execute()
            return
        except Exception as e:
            print(f"Erreur Supabase insert: {e}")
    if chat_id not in conversations_cache:
        conversations_cache[chat_id] = []
    conversations_cache[chat_id].append({"role": role, "content": message})
    if len(conversations_cache[chat_id]) > 20:
        conversations_cache[chat_id] = conversations_cache[chat_id][-20:]

# ========== PROTECTION ANTI-SPAM ==========
last_message_time = {}
RATE_LIMIT_SECONDS = 2

def is_rate_limited(chat_id):
    now = time.time()
    if chat_id in last_message_time:
        if now - last_message_time[chat_id] < RATE_LIMIT_SECONDS:
            return True
    last_message_time[chat_id] = now
    return False

# ========== DÉTECTION DE TRANSFERT ==========
TRANSFER_KEYWORDS = [
    "humain", "gérant", "responsable", "patron", "moussa",
    "trop cher", "négocier", "remise", "réduction",
    "payer", "paiement", "mobile money", "orange money", "mtn",
    "réclamation", "problème", "remboursement", "arnaque"
]

def needs_transfer(message):
    msg = message.lower()
    return any(keyword in msg for keyword in TRANSFER_KEYWORDS)

# ========== ENVOI WHATSAPP ==========
def send_whatsapp(to, body):
    url = f"https://api.ultramsg.com/{ULTRAMSG_INSTANCE_ID}/messages/chat"
    payload = {"token": ULTRAMSG_TOKEN, "to": to, "body": body}
    try:
        response = requests.post(url, data=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Erreur envoi WhatsApp: {e}")
        return None

# ========== ALERTE MULTI-CANAUX ==========
def notify_moussa(client_name, client_number, products, objection, last_message):
    print(f"DEBUG - Token: {TELEGRAM_BOT_TOKEN}, Chat ID: {TELEGRAM_CHAT_ID}")
    alert_text = (
        f"🔔 NOUVEAU TRANSFERT\n\n"
        f"👤 Client : {client_name}\n"
        f"📞 Numéro : {client_number}\n"
        f"🛍️ Produits : {products}\n"
        f"⚠️ Objection : {objection}\n"
        f"💬 Dernier message : {last_message}"
    )
    # WhatsApp
    send_whatsapp(MOUSSA_WHATSAPP, alert_text)
    # Telegram
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": alert_text},
                timeout=10
            )
            print(f"Réponse Telegram: {response.text}")
        except Exception as e:
            print(f"Erreur Telegram: {e}")

# ========== WEBHOOK ==========2q
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        if not data or "data" not in data:
            return jsonify({"status": "ignored"}), 200
        
        message_data = data["data"]
        chat_id = message_data.get("from")
        body = message_data.get("body", "")
        sender_name = message_data.get("senderName", "Client")
        msg_type = message_data.get("type", "chat")
        
        if not chat_id or not body:
            return jsonify({"status": "ignored"}), 200
        
        # Anti-spam
        if is_rate_limited(chat_id):
            return jsonify({"status": "rate_limited"}), 200
        
        # Détection de transfert
        if needs_transfer(body):
            send_whatsapp(chat_id, "Je transmets votre demande à M. Garba. Il vous répond dans quelques minutes. Merci de votre patience.")
            notify_moussa(sender_name, chat_id, "À préciser", "Négociation / Demande humaine", body)
            add_to_conversation(chat_id, "user", body, sender_name)
            return jsonify({"status": "transferred"}), 200
        
        # Sauvegarde du message
        add_to_conversation(chat_id, "user", body, sender_name)
        history = get_conversation(chat_id)
        
        # Construction du prompt
        prompt = SYSTEM_PROMPT + "\n\nHistorique de la conversation :\n"
        for msg in history[-10:]:
            prompt += f"{msg['role']}: {msg['content']}\n"
        prompt += f"\nClient : {body}\nAssistant :"
        
        # Génération de la réponse
        try:
            response = model.generate_content(prompt)
            ai_reply = response.text.strip()
        except Exception as e:
            ai_reply = "Je suis désolé, je rencontre un petit souci technique. Je transmets votre message à M. Garba."
            notify_moussa(sender_name, chat_id, "Erreur technique", str(e), body)
        
        add_to_conversation(chat_id, "assistant", ai_reply, "Assistant")
        send_whatsapp(chat_id, ai_reply)
        
        return jsonify({"status": "ok"}), 200
    
    except Exception as e:
        print(f"Erreur webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "alive", "bot": "Market237Lion"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
