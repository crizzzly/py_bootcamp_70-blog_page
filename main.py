import os
import re
from urllib.parse import urlparse, urljoin

import bleach as bleach
import sqlalchemy
from flask import Flask, render_template, redirect, url_for, flash, request, abort, g
from flask_bootstrap import Bootstrap
from flask_ckeditor import CKEditor
from datetime import date
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from flask_login import UserMixin, login_user, LoginManager, login_required, current_user, logout_user
from flask_gravatar import Gravatar
from forms import CreatePostForm, CreateRegisterForm, CreateLoginForm, CreateCommentForm
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("FLASK_SECRET_KEY")
ckeditor = CKEditor(app)
Bootstrap(app)

##CONNECT TO DB
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)

tag_cleaner = re.compile('<.*?>')

gravatar = Gravatar(app,
                    size=50,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)


##CONFIGURE TABLE
class BlogPost(db.Model):
	__tablename__ = "blog_posts"
	id = db.Column(db.Integer, primary_key=True)
	author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
	author = relationship("User", back_populates="posts")

	title = db.Column(db.String(250), unique=True, nullable=False)
	subtitle = db.Column(db.String(250), nullable=False)
	date = db.Column(db.String(250), nullable=False)
	body = db.Column(db.Text, nullable=False)
	img_url = db.Column(db.String(250), nullable=False)
	comments = relationship("Comment", back_populates="parent_post")


class User(UserMixin, db.Model):
	__tablename__ = "user"
	id = db.Column(db.Integer, primary_key=True)
	email = db.Column(db.String(100), unique=True)
	password = db.Column(db.String(100))
	name = db.Column(db.String(1000))
	posts = relationship("BlogPost", back_populates="author")
	comments = relationship("Comment", back_populates="comment_author")

	def is_authenticated(self):
		return self.is_authenticated()

	def is_active(self):
		return self.is_active()

	def is_anonymous(self):
		return self.is_anonymous()

	def get_id(self):
		return str(self.id)


class Comment(db.Model):
	__tablename__ = "comments"
	comment_author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
	parent_post_id = db.Column(db.Integer, db.ForeignKey("blog_posts.id"))
	comment_author = relationship("User", back_populates="comments")
	parent_post = relationship("BlogPost", back_populates="comments")
	id = db.Column(db.Integer, primary_key=True)
	text = db.Column(db.Text, nullable=False)


# with app.app_context():
# 	db.create_all()


# strips invalid tags/attributes
def strip_invalid_html(content):
	allowed_tags = ['a', 'abbr', 'acronym', 'address', 'b', 'br', 'div', 'dl', 'dt', 'em', 'h1', 'h2', 'h3', 'h4', 'h5',
	                'h6', 'hr', 'i', 'img', 'li', 'ol', 'p', 'pre', 'q', 's', 'small', 'strike', 'span', 'sub', 'sup',
	                'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'tr', 'tt', 'u', 'ul']

	allowed_attrs = {
		'a': ['href', 'target', 'title'],
		'img': ['src', 'alt', 'width', 'height'],
	}

	cleaned = bleach.clean(content,
	                       tags=allowed_tags,
	                       attributes=allowed_attrs,
	                       strip=True
	                       )

	return cleaned


def is_save_url(target):
	ref_url = urlparse(request.host_url)
	test_url = urlparse(urljoin(request.host_url, target))
	return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


# admin_only_decorater-func
def admin_only(f):
	@wraps(f)
	def decorated_function(*args, **kwargs):
		if current_user.id == 1:
			print(request.url)
			target = request.url.split('/')[-1].replace('-', '_')
			return f(*args, **kwargs)
		else:
			return abort(403)

	return decorated_function


@login_manager.user_loader
def load_user(user_id):
	return User.query.get(user_id)


@app.route('/')
def get_all_posts():
	posts = BlogPost.query.all()
	return render_template("index.html", all_posts=posts)


@app.route('/register', methods=["GET", "POST"])
def register():
	register_form = CreateRegisterForm()
	if register_form.validate_on_submit():
		password = generate_password_hash(register_form.password.data, salt_length=8)
		user = User(
			email=register_form.email.data,
			password=password,
			name=register_form.name.data
		)
		try:
			db.session.add(user)
			db.session.commit()
		except sqlalchemy.exc.IntegrityError:
			flash("Email already exists")
			return redirect(url_for('login'))
		finally:
			return redirect(url_for('login'))
	else:
		return render_template("register.html", form=register_form)


@app.route('/login', methods=["GET", "POST"])
def login():
	login_form = CreateLoginForm()
	error = request.args.get('error')
	if login_form.validate_on_submit():
		user = User.query.filter_by(email=login_form.email.data).first()
		try:
			load_user(user.id)
		except AttributeError as e:
			flash("User does not exist")
			return render_template("login.html", form=login_form)
		else:
			if check_password_hash(user.password, login_form.password.data):
				login_user(user)
				flash("logged in successfully")

				next_site = request.args.get('next')
				print(f'next: {next_site}')
				if not is_save_url(next_site):
					return abort(400)
				else:
					return redirect(next_site or url_for('get_all_posts', name=user.name))
			else:
				flash("Wrong password")
				return render_template('login.html', form=login_form)
	flash(error)
	return render_template("login.html", form=login_form)


@app.route('/logout')
def logout():
	logout_user()
	return redirect(url_for('get_all_posts'))


@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
	# requested_post = db.session.query(BlogPost).filter_by(id=index).first()
	requested_post = BlogPost.query.get(post_id)
	comment_form = CreateCommentForm()
	if comment_form.validate_on_submit():
		if not current_user.is_authenticated:
			flash("You need to login to make a comment")
			return redirect(url_for("login"))
		text = strip_invalid_html(comment_form.comment.data)
		comment = Comment(
			text=text,
			comment_author=current_user,
			parent_post=requested_post,
		)
		if len(text) > 0:
			db.session.add(comment)
			db.session.commit()
		comment_form.comment.data = ""
		return redirect(url_for("show_post", post_id=post_id))
	# comments = Comment.query.all()
	# return render_template("post.html", post=requested_post, comment_form=comment_form, comments=comments)
	comments = Comment.query.all()

	return render_template("post.html", post=requested_post, comment_form=comment_form)


@app.route("/edit/<int:post_id>", methods=["GET", "PATCH", "PUT", "POST"])
@login_required
@admin_only
def edit_post(post_id):
	# post = BlogPost.query.filter_by(id=post_id).scalar_one()
	# post = db.session.execute(select(BlogPost).filter_by(id=post_id)).scalar_one()
	post = BlogPost.query.get(post_id)
	form = CreatePostForm()

	if form.validate_on_submit():
		post.title = form.title.data
		post.subtitle = form.subtitle.data
		post.body = form.body.data
		post.img_url = form.img_url.data
		post.author = form.author.data
		db.session.commit()
		return redirect(url_for('show_post', post_id=post.id))
	else:
		form.title.data = post.title
		form.subtitle.data = post.subtitle
		form.body.data = post.body
		form.author.data = post.author
		form.img_url.data = post.img_url
		return render_template("make-post.html", form=form, headline="Edit Post")


@app.route("/new-post", methods=["GET", "POST"])
@login_required
@admin_only
def new_post():
	post_form = CreatePostForm()
	if post_form.validate_on_submit():
		print(post_form.title.data)
		new = BlogPost(
			title=post_form.title.data,
			subtitle=post_form.subtitle.data,
			date=date.today().strftime("%B %d, %Y"),
			body=post_form.body.data,
			author=current_user,
			img_url=post_form.img_url.data,
		)
		db.session.add(new)
		db.session.commit()
		return redirect(url_for('get_all_posts'))
	return render_template("make-post.html", form=post_form, headline="New Post")


@app.route("/delete/<int:post_id>")
@login_required
@admin_only
def delete_post(post_id):
	post = BlogPost.query.get(post_id)
	db.session.delete(post)
	db.session.commit()
	return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
	return render_template("about.html")


@app.route("/contact")
def contact():
	return render_template("contact.html")


if __name__ == "__main__":
	app.run(host='0.0.0.0', port=5001, debug=True)
