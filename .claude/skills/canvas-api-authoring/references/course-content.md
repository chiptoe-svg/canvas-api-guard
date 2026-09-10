# Course content

Announcements, pages, modules and the module items inside them, the course home page, and
which navigation tabs a student actually sees. An announcement and a page each turn out to be
two settings that must agree, not one; both traps are called out explicitly below.

### Posting an announcement

**What Canvas does.** An announcement is not a separate Canvas object. `announcements.html`
says so directly: "This API is Announcement-specific. See also the Discussion Topics API, which
operates on Announcements also," and every example response on that page is a `DiscussionTopic`.
The page documents exactly one endpoint, a read-only `GET` that lists announcements across one
or more courses at once. An announcement is created the same way any discussion topic is
created — on `discussion_topics.html`'s create endpoint — by setting `is_announcement` to true,
which "requires announcment-posting permissions" and moves the topic "into the announcement's
section rather than the discussions section." The same course's announcements can also be
listed from inside the discussion topics list endpoint with `only_announcements=true`, a second,
course-scoped way to the same objects.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/courses/:course_id/discussion_topics` | Create a discussion topic, or an announcement when `is_announcement=true` |
| PUT | `/api/v1/courses/:course_id/discussion_topics/:topic_id` | Update a topic, including toggling `is_announcement` |
| GET | `/api/v1/courses/:course_id/discussion_topics` | List topics in a course; `only_announcements=true` returns announcements only |
| GET | `/api/v1/announcements` | List announcements across one or more courses (read-only) |

**Parameters.**
- `title`, `message` — string, discussion topic create/update.
- `is_announcement` — boolean, discussion topic create/update; "If true, this topic is an
  announcement."
- `published` — boolean, discussion topic create/update.
- `specific_sections` — string, discussion topic create/update.
- `lock_comment` — boolean, discussion topic create/update.
- `podcast_enabled`, `podcast_has_student_posts` — boolean, discussion topic create/update.
- `only_announcements` — boolean, discussion topic list-only.
- `context_codes[]` — string, `Required`, announcements list-only.
- `include` — array, announcements list-only. Allowed values: `sections`,
  `sections_user_count`.

**Traps.**
- `announcements.html` documents exactly one endpoint, a `GET`, and no create, update, or
  delete verb anywhere on the page. A caller looking on this page for the announcement create
  call will not find one; creation happens on `discussion_topics.html`'s create endpoint with
  `is_announcement=true` (docs: https://canvas.instructure.com/doc/api/announcements.html; docs:
  https://canvas.instructure.com/doc/api/discussion_topics.html).
- `specific_sections` "Can only be present only on announcements and only those that are for a
  course (as opposed to a group)" — section-scoping only works for course announcements, not
  group ones, and only when `is_announcement` is true, not on an ordinary discussion topic
  (docs: https://canvas.instructure.com/doc/api/discussion_topics.html).
- `lock_comment` only has a documented effect "If is_announcement and lock_comment are true" —
  sending it on an ordinary discussion topic has no stated effect (docs:
  https://canvas.instructure.com/doc/api/discussion_topics.html).
- `context_codes[]` on the announcements list "Only courses are presently supported" even
  though the parameter name is generic — group announcements cannot be listed through this
  endpoint (docs: https://canvas.instructure.com/doc/api/announcements.html).

**Source.** https://canvas.instructure.com/doc/api/announcements.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/discussion_topics.html, fetched 2026-09-10

### Delaying an announcement until a date

**What Canvas does.** Both create and update on `discussion_topics.html` carry
`delayed_post_at`: "If a timestamp is given, the topic will not be published until that time."
That is the field that delays an announcement's first appearance, and it is the same field
ordinary discussion topics use — nothing about its name is announcement-specific. A second,
separate field, `lock_at`, "will be scheduled to lock" the topic for comments; it governs when
discussion closes, not when the announcement first appears. `announcements.html`'s own list
endpoint reflects delayed posting from the reader's side: `start_date`/`end_date` filter by
`posted_at`, and "Announcements scheduled for future posting will only be returned to course
administrators" — a student querying the same window will not see them yet.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/courses/:course_id/discussion_topics` | Create a topic or announcement with a future `delayed_post_at` |
| PUT | `/api/v1/courses/:course_id/discussion_topics/:topic_id` | Change `delayed_post_at` or `lock_at` on an existing one |
| GET | `/api/v1/announcements` | List announcements, filtered by `start_date`/`end_date`/`available_after` |

**Parameters.**
- `delayed_post_at` — DateTime, discussion topic create/update; "the topic will not be published
  until that time."
- `lock_at` — DateTime, discussion topic create/update; "the topic will be scheduled to lock."
- `start_date`, `end_date` — Date, announcements list-only.
- `available_after` — Date, announcements list-only; "Effective only for students (who don't
  have moderate forum right)."

**Traps.**
- `delayed_post_at` delays when a topic is *posted*; `lock_at` is a separate field that governs
  when it locks for comments. Nothing on the page says setting one affects the other, and a
  topic can carry both at once, pointed at different dates (docs:
  https://canvas.instructure.com/doc/api/discussion_topics.html).
- `available_after` is "Effective only for students (who don't have moderate forum right)" — an
  instructor's own read of the same announcement is not filtered by it the same way (docs:
  https://canvas.instructure.com/doc/api/announcements.html).
- `start_date` "Defaults to 14 days ago" and `end_date` "Defaults to 28 days from start_date" —
  a caller who omits both expecting "every announcement" instead gets a roughly six-week window
  (docs: https://canvas.instructure.com/doc/api/announcements.html).

**Source.** https://canvas.instructure.com/doc/api/discussion_topics.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/announcements.html, fetched 2026-09-10

### Creating a page

**What Canvas does.** A page is created inside a course (or group) with a required `title`;
everything else is optional. Pages are identified in later calls by either a numeric id or a
URL slug, and the documentation warns these can collide: "if you have a page whose ID is 7 and
another whose ID is 8 and whose URL is '7', the endpoint `/api/v1/courses/:course_id/pages/7`
will refer to the latter (ID 8)" — the URL wins the ambiguity, and `page_id:7` is the documented
way to force an id lookup.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/courses/:course_id/pages` | Create a new wiki page |
| GET | `/api/v1/courses/:course_id/pages` | List pages in a course |
| GET | `/api/v1/courses/:course_id/pages/:url_or_id` | Retrieve a wiki page |

**Parameters.**
- `wiki_page[title]` — string, `Required` on create.
- `wiki_page[body]` — string.
- `wiki_page[editing_roles]` — string. Allowed values: `teachers`, `students`, `members`,
  `public`.
- `wiki_page[notify_of_update]` — boolean.
- `wiki_page[published]` — boolean.
- `wiki_page[front_page]` — boolean, create/update; "Set an unhidden page as the front page (if
  true)."
- `wiki_page[publish_at]` — DateTime, create/update.
- `sort`, `order`, `search_term`, `published` — list-only.

**Traps.**
- The page-identifier ambiguity example is literal: a request for `/pages/7` can resolve to a
  page whose id is 8, because "the URL takes precedence" over the id whenever both exist. Code
  that assumes a numeric path segment always means the numeric id will fetch the wrong page
  (docs: https://canvas.instructure.com/doc/api/pages.html).
- `wiki_page[front_page]`'s entire documented condition is "Set an unhidden page as the front
  page (if true)" — the page never defines what "unhidden" means for this purpose or what
  happens when it is sent for a hidden one (docs:
  https://canvas.instructure.com/doc/api/pages.html).

**Source.** https://canvas.instructure.com/doc/api/pages.html, fetched 2026-09-10

### Editing a page, and its url versus its title

**What Canvas does.** Editing a page's `title` or `body` uses the same update endpoint whether
the caller identifies the page by id or by url. The documentation is explicit about one
consequence: "changing a page's title will change its url. The updated url will be returned in
the result." Past versions of a page are read back through a separate revisions endpoint, and
restored with a dedicated revert call rather than by editing history directly.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| PUT | `/api/v1/courses/:course_id/pages/:url_or_id` | Update the title or contents of a wiki page |
| GET | `/api/v1/courses/:course_id/pages/:url_or_id/revisions` | List revisions |
| GET | `/api/v1/courses/:course_id/pages/:url_or_id/revisions/latest` | Show the latest revision |
| GET | `/api/v1/courses/:course_id/pages/:url_or_id/revisions/:revision_id` | Show one revision |
| POST | `/api/v1/courses/:course_id/pages/:url_or_id/revisions/:revision_id` | Revert to a prior revision |

**Parameters.**
- `wiki_page[title]` — string, update; "changing a page's title will change its url."
- `wiki_page[body]` — string, update.
- `revision_id` — path segment identifying a specific `PageRevision`.
- `summary` — boolean, revision show-only; "the following fields are not included in the index
  action and may be omitted from the show action via summary=1."

**Traps.**
- Changing `wiki_page[title]` changes the page's url as a documented side effect. A caller that
  has cached a page's url for later lookups must re-read the response after any title edit, or
  its next request by the old url will not resolve (docs:
  https://canvas.instructure.com/doc/api/pages.html).
- "You cannot specify the ID when creating a page. If you pass a numeric value as the page
  identifier and that does not represent a page ID that already exists, it will be interpreted
  as a URL" — this note sits under Update/create page, meaning a `PUT` to a numeric-looking
  `url_or_id` that doesn't match an existing id creates a new page whose literal url is that
  numeral, not a page with that id (docs: https://canvas.instructure.com/doc/api/pages.html).
- Nothing on the page documents editing or deleting one specific historic revision directly —
  the only documented way back to an old body is the revert endpoint, which itself returns a
  fresh `Page` object rather than the `PageRevision` it reverted to (docs:
  https://canvas.instructure.com/doc/api/pages.html).

**Source.** https://canvas.instructure.com/doc/api/pages.html, fetched 2026-09-10

### Publishing a page

**What Canvas does.** `wiki_page[published]` is a plain boolean on the same create/update
endpoint as everything else about a page. `wiki_page[publish_at]` layers a scheduled variant on
top of it, but the two endpoints describe the interaction differently: create's description says
"If a future date is supplied, the page will be unpublished and `wiki_page[published]` will be
ignored," while update's says "If a future date is set and the page is already published, it
will be unpublished" — update's wording is conditioned on the page's current state in a way
create's is not.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/courses/:course_id/pages` | Create a page, optionally scheduled |
| PUT | `/api/v1/courses/:course_id/pages/:url_or_id` | Publish, unpublish, or reschedule a page |

**Parameters.**
- `wiki_page[published]` — boolean, create/update; "whether the page is published (true) or
  draft state (false)."
- `wiki_page[publish_at]` — DateTime, create/update; "This will have no effect unless the
  'Scheduled Page Publication' feature is enabled in the account."
- `hide_from_students` — boolean, response field only; "(DEPRECATED) whether this page is
  hidden from students (note: this is always reflected as the inverse of the published value)."

**Traps.**
- `wiki_page[publish_at]` "will have no effect unless the 'Scheduled Page Publication' feature
  is enabled in the account" — setting it on an account without that feature does nothing,
  silently, with no documented error (docs: https://canvas.instructure.com/doc/api/pages.html).
- Create's and update's prose for `wiki_page[publish_at]` describe its interaction with
  publishing in different terms — create says a future date makes `wiki_page[published]` itself
  be ignored; update says a future date unpublishes a page that "is already published." Neither
  endpoint states what happens on update if `publish_at` is set to a future date on a page that
  is *not* already published (docs: https://canvas.instructure.com/doc/api/pages.html).
- `hide_from_students` is documented "always... the inverse of the published value" and has no
  request parameter of its own — only `wiki_page[published]` can be set; sending
  `hide_from_students` directly is not documented to do anything (docs:
  https://canvas.instructure.com/doc/api/pages.html).

**Source.** https://canvas.instructure.com/doc/api/pages.html, fetched 2026-09-10

### Making a page the course home page

**What Canvas does.** Two separate settings decide what a student lands on when they open a
course, and the two fetched pages never cross-reference each other. `wiki_page[front_page]`
(the page create/update endpoint, `pages.html`) designates which single page is the wiki's front
page: "Set an unhidden page as the front page (if true)." `course[default_view]` (the course
create/update endpoint, `courses.html`) is what actually decides which kind of screen a course
shows first at all; its literal, verbatim allowed values are `feed`, `wiki`, `modules`,
`syllabus`, `assignments`, described respectively as "Recent Activity Dashboard," "Wiki Front
Page," "Course Modules/Sections Page," "Course Syllabus Page," and "Course Assignments List." A
front page only appears as the course home page when `default_view` is set to `wiki`; setting
either one without the other gets a course whose home page is not what the caller intended.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:course_id/front_page` | Retrieve the content of the current front page |
| PUT | `/api/v1/courses/:course_id/front_page` | Update the *content* of the current front page |
| POST | `/api/v1/courses/:course_id/pages` | Create a page and, optionally, mark it the front page |
| PUT | `/api/v1/courses/:course_id/pages/:url_or_id` | Mark an existing page the front page |
| POST | `/api/v1/accounts/:account_id/courses` | Create a course, with a `default_view` |
| PUT | `/api/v1/courses/:id` | Change a course's `default_view` |

**Parameters.**
- `wiki_page[front_page]` — boolean, page create/update; "Set an unhidden page as the front page
  (if true)."
- `course[default_view]` — string, course create/update. Allowed values: `feed`, `wiki`,
  `modules`, `syllabus`, `assignments`.

**Traps.**
- The dedicated `PUT /api/v1/courses/:course_id/front_page` endpoint's own parameter table has
  no `wiki_page[front_page]` field at all — it only carries `wiki_page[title]`,
  `wiki_page[body]`, `wiki_page[editing_roles]`, `wiki_page[notify_of_update]`, and
  `wiki_page[published]`. It edits whichever page is *already* the front page; designating a
  *different* page as front page happens on the ordinary page create or update endpoint's own
  `wiki_page[front_page]` parameter, not here (docs:
  https://canvas.instructure.com/doc/api/pages.html).
- The create-course endpoint's own descriptive bullets for `course[default_view]` list only
  `'feed'`, `'modules'`, `'assignments'`, `'syllabus'` — `wiki` is missing from that prose —
  while the same field's Allowed-values list on that same endpoint does include `wiki`. The
  update-course endpoint's prose bullets, by contrast, list all five including `'wiki' Wiki
  Front Page` (docs: https://canvas.instructure.com/doc/api/courses.html).
- Neither `pages.html` nor `courses.html` documents what happens if only one of the two settings
  is made: `wiki_page[front_page]=true` with `default_view` left as something other than `wiki`
  leaves the marked page unseen as a home page, and `default_view=wiki` with no page carrying
  `front_page=true` is not addressed by either page at all (docs:
  https://canvas.instructure.com/doc/api/pages.html; docs:
  https://canvas.instructure.com/doc/api/courses.html).

**Source.** https://canvas.instructure.com/doc/api/pages.html, fetched 2026-09-10; https://canvas.instructure.com/doc/api/courses.html, fetched 2026-09-10

### Building a module

**What Canvas does.** A module is a named, positioned container inside a course, created with
one required field, `module[name]`. `module[prerequisite_module_ids][]` chains modules together
and `module[unlock_at]` gates one by date; `module[require_sequential_progress]` and
`module[publish_final_grade]` are plain booleans on the same object. If any active
`AssignmentOverride` exists on a module, "then only students who have an applicable override can
access the module and are assigned its items" — a module can itself be scoped the same way an
assignment is.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:course_id/modules` | List modules in a course |
| GET | `/api/v1/courses/:course_id/modules/:id` | Show one module |
| POST | `/api/v1/courses/:course_id/modules` | Create a module |
| PUT | `/api/v1/courses/:course_id/modules/:id` | Update a module |
| DELETE | `/api/v1/courses/:course_id/modules/:id` | Delete a module |
| PUT | `/api/v1/courses/:course_id/modules/:id/relock` | Reset and recalculate module progressions |

**Parameters.**
- `module[name]` — string, `Required` on create.
- `module[unlock_at]` — DateTime.
- `module[position]` — integer.
- `module[require_sequential_progress]` — boolean.
- `module[prerequisite_module_ids][]` — string (array); "Prerequisite modules must precede this
  module (i.e. have a lower position value), otherwise they will be ignored."
- `module[publish_final_grade]` — boolean.
- `module[published]` — boolean, update-only.

**Traps.**
- `module[prerequisite_module_ids][]` documents its own failure mode: a module whose position is
  not lower than the module being created "will be ignored" as a prerequisite, silently, with no
  error (docs: https://canvas.instructure.com/doc/api/modules.html).
- `module[published]` appears only in the Update module endpoint's parameter table, not
  Create's — there is no documented way to publish a module in the same call that creates it
  (docs: https://canvas.instructure.com/doc/api/modules.html).
- The relock endpoint exists precisely because publishing is not retroactive: "Adding
  progression requirements to an active course will not lock students out of modules they have
  already unlocked unless this action is called" (docs:
  https://canvas.instructure.com/doc/api/modules.html).

**Source.** https://canvas.instructure.com/doc/api/modules.html, fetched 2026-09-10

### Putting things in a module

**What Canvas does.** A module item wraps a reference to some other piece of content —
`module_item[type]` names which kind, and its literal, verbatim allowed values are `File`,
`Page`, `Discussion`, `Assignment`, `Quiz`, `SubHeader`, `ExternalUrl`, `ExternalTool`.
`module_item[content_id]` points at the underlying object and is "Required, except for
'ExternalUrl', 'Page', and 'SubHeader' types" — the inverse case, `module_item[page_url]`, is
"Required for 'Page' type" instead of a content id. `module_item[indent]` is a "0-based indent
level" used only to show hierarchy in the module's display; it does not itself nest one item's
completion inside another's.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:course_id/modules/:module_id/items` | List items in a module |
| GET | `/api/v1/courses/:course_id/modules/:module_id/items/:id` | Show one module item |
| POST | `/api/v1/courses/:course_id/modules/:module_id/items` | Create a module item |
| PUT | `/api/v1/courses/:course_id/modules/:module_id/items/:id` | Update a module item |
| DELETE | `/api/v1/courses/:course_id/modules/:module_id/items/:id` | Delete a module item |

**Parameters.**
- `module_item[title]` — string.
- `module_item[type]` — string, `Required` on create. Allowed values: `File`, `Page`,
  `Discussion`, `Assignment`, `Quiz`, `SubHeader`, `ExternalUrl`, `ExternalTool`.
- `module_item[content_id]` — string, `Required` on create except for `ExternalUrl`, `Page`, and
  `SubHeader` types.
- `module_item[position]` — integer.
- `module_item[indent]` — integer; "0-based indent level."
- `module_item[page_url]` — string, create-only; "Required for 'Page' type."
- `module_item[external_url]` — string; "Required for 'ExternalUrl' and 'ExternalTool' types."
- `module_item[new_tab]` — boolean; "Only applies to 'ExternalTool' type."
- `module_item[iframe][width]`, `module_item[iframe][height]` — integer, create-only.
- `module_item[module_id]` — string, update-only; "Move this item to another module... The
  target module must be in the same course."

**Traps.**
- `module_item[type]` is required on create and has no equivalent field on update at all — an
  item's type is fixed for its lifetime through this API; changing what kind of content it
  points at means deleting and recreating the item (docs:
  https://canvas.instructure.com/doc/api/modules.html).
- `module_item[content_id]` and `module_item[page_url]` are both create-only; update's parameter
  table has neither. Only `title`, `position`, `indent`, `external_url`, `new_tab`,
  `completion_requirement`, `published`, and `module_id` can change on an existing item — the
  content or page it points at cannot be repointed (docs:
  https://canvas.instructure.com/doc/api/modules.html).
- `module_item[content_id]`'s required-except list (`ExternalUrl`, `Page`, `SubHeader`) and
  `module_item[page_url]`'s required-for list (`Page`) partition the eight types in opposite
  directions; neither field is simply optional for every type (docs:
  https://canvas.instructure.com/doc/api/modules.html).
- `module_item[module_id]` moves an item between modules on update, but "The target module must
  be in the same course" — a cross-course move is not documented as possible through this field
  (docs: https://canvas.instructure.com/doc/api/modules.html).

**Source.** https://canvas.instructure.com/doc/api/modules.html, fetched 2026-09-10

### Requirements and prerequisites

**What Canvas does.** A completion requirement is set per module item, not per module:
`module_item[completion_requirement][type]` names the kind of requirement, gated by content
type — "'must_view': Applies to all item types," "'must_contribute': Only applies to
'Assignment', 'Discussion', and 'Page' types," "'must_submit', 'min_score': Only apply to
'Assignment' and 'Quiz' types," "'must_mark_done': Only applies to 'Assignment', 'Page', and
'AiExperience' types," and "Inapplicable types will be ignored." A module's own
`module[prerequisite_module_ids][]` and `module[require_sequential_progress]` are a separate,
module-level pair of gates layered on top of any item-level requirements.

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/courses/:course_id/modules/:module_id/items` | Set a completion requirement when creating an item |
| PUT | `/api/v1/courses/:course_id/modules/:module_id/items/:id` | Change a completion requirement |
| POST | `/api/v1/courses/:course_id/modules` | Set a module's own sequencing and prerequisites |
| PUT | `/api/v1/courses/:course_id/modules/:id` | Change a module's sequencing and prerequisites |

**Parameters.**
- `module_item[completion_requirement][type]` — string. Allowed values: `must_view`,
  `must_contribute`, `must_submit`, `must_mark_done`.
- `module_item[completion_requirement][min_score]` — integer; "Required for completion_requirement
  type 'min_score'."
- `module[require_sequential_progress]` — boolean.
- `module[prerequisite_module_ids][]` — string (array).

**Traps.**
- `module_item[completion_requirement][type]`'s own literal Allowed-values list is exactly four
  entries — `must_view`, `must_contribute`, `must_submit`, `must_mark_done` — but the field's
  prose description above that list names `min_score` as a fifth requirement kind ("'must_submit',
  'min_score': Only apply to 'Assignment' and 'Quiz' types"), and the separate
  `module_item[completion_requirement][min_score]` parameter is documented "Required for
  completion_requirement type 'min_score'." `min_score` is clearly meant to be settable, but it
  does not appear in the field's own Allowed-values enumeration (docs:
  https://canvas.instructure.com/doc/api/modules.html). The same gap holds for `min_percentage`:
  the `CompletionRequirement` response object's own schema comment lists the `type` field as "one
  of 'must_view', 'must_submit', 'must_contribute', 'min_score', 'min_percentage',
  'must_mark_done'" and documents a matching `min_percentage` field ("minimum percentage required
  to complete (only present when type == 'min_percentage')"), but `min_percentage` is absent from
  both the create/update Allowed-values list and from this page's own
  `module_item[completion_requirement][...]` request parameters — there is no documented request
  parameter to set it (docs: https://canvas.instructure.com/doc/api/modules.html).
- `must_mark_done`'s prose scopes it to "'Assignment', 'Page', and 'AiExperience'" types, but
  `AiExperience` never appears in `module_item[type]`'s own Allowed-values list (`File`, `Page`,
  `Discussion`, `Assignment`, `Quiz`, `SubHeader`, `ExternalUrl`, `ExternalTool`) — a module item
  cannot be created with that type through this endpoint even though a completion requirement
  can name it (docs: https://canvas.instructure.com/doc/api/modules.html).
- "Inapplicable types will be ignored" — setting `must_contribute` on a `Quiz` item is accepted
  syntactically but, per this sentence, does nothing; there is no documented validation error for
  the mismatch (docs: https://canvas.instructure.com/doc/api/modules.html).
- `module[require_sequential_progress]` and `module[prerequisite_module_ids][]` are independent
  fields; nothing on the page states that one implies or requires the other. A module can gate
  entry by prerequisite modules without gating item order inside it, or the reverse (docs:
  https://canvas.instructure.com/doc/api/modules.html).

**Source.** https://canvas.instructure.com/doc/api/modules.html, fetched 2026-09-10

### Publishing a module, and what that does to its items

**What Canvas does.** `module[published]` and `module_item[published]` are two separate
booleans on two separate objects, each present only on its own Update endpoint's parameter
table. Marking a module item read or done is blocked on publication state: the mark-read
endpoint states "This endpoint cannot be used to complete requirements on locked or unpublished
module items." Re-locking students out of a module after its requirements change is not
automatic; it needs the dedicated relock call described in "Building a module."

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| PUT | `/api/v1/courses/:course_id/modules/:id` | Publish or unpublish a module |
| PUT | `/api/v1/courses/:course_id/modules/:module_id/items/:id` | Publish or unpublish one module item |
| PUT | `/api/v1/courses/:course_id/modules/:module_id/items/:id/done` | Mark a module item done (or, via `DELETE`, not done) |
| POST | `/api/v1/courses/:course_id/modules/:module_id/items/:id/mark_read` | Fulfill a "must view" requirement directly |

**Parameters.**
- `module[published]` — boolean, update-only; "Whether the module is published and visible to
  students."
- `module_item[published]` — boolean, update-only; "Whether the module item is published and
  visible to students."

**Traps.**
- Neither `module[published]` nor `module_item[published]` appears on its object's Create
  endpoint — only Update. There is no documented way to publish a module, or a module item, in
  the same call that creates it (docs: https://canvas.instructure.com/doc/api/modules.html).
- Nothing on the page states that publishing a module publishes the items inside it, or that an
  unpublished module hides published items inside it — the two flags are documented completely
  independently of one another (docs: https://canvas.instructure.com/doc/api/modules.html).
- The `mark_read` endpoint's own note — "cannot be used to complete requirements on locked or
  unpublished module items" — means a student-facing completion call silently cannot satisfy a
  requirement until the instructor has published both the module and the item (docs:
  https://canvas.instructure.com/doc/api/modules.html).
- Re-locking is deliberately not automatic: "Adding progression requirements to an active course
  will not lock students out of modules they have already unlocked unless this action is
  called," naming the separate relock endpoint. Publishing a module, or editing its
  requirements, does not retroactively apply to students already inside it on its own (docs:
  https://canvas.instructure.com/doc/api/modules.html).

**Source.** https://canvas.instructure.com/doc/api/modules.html, fetched 2026-09-10

### Which tabs students see

**What Canvas does.** A course's navigation tabs are read back as a list of `Tab` objects, each
with a `type` (`internal` or `external`), a `position`, and a `visibility`, whose literal,
verbatim documented values are "public, members, admins, and none." A tab's `hidden` field is
"only included if true" in the response — a visible tab simply omits the key rather than
carrying `hidden: false`. Only two of a tab's fields can be changed through this API: its
`position` and whether it is `hidden`. "Home and Settings tabs are not manageable, and can't be
hidden or moved."

**Endpoints.**

| Verb | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/courses/:course_id/tabs` | List navigation tabs for a course |
| PUT | `/api/v1/courses/:course_id/tabs/:tab_id` | Hide, show, or reposition one tab |

**Parameters.**
- `include[]` — string, list-only. Allowed values: `course_subject_tabs`.
- `position` — integer, update; "The new position of the tab, 1-based."
- `hidden` — boolean, update.
- `visibility` — string, response field only. Allowed values (as documented): `public`,
  `members`, `admins`, `none`.
- `type` — string, response field only. Values shown: `internal`, `external`.

**Traps.**
- `hidden` is "only included if true" in the response — code that reads `tab["hidden"]` without
  a default will fail on every tab that is currently visible, since the key is absent rather
  than `false` (docs: https://canvas.instructure.com/doc/api/tabs.html).
- `visibility` and `hidden` answer different questions and can combine: a tab whose computed
  `visibility` is `admins` is not the same thing as one an admin has manually set `hidden:
  true` — an admins-only tab can also be hidden on top of that (docs:
  https://canvas.instructure.com/doc/api/tabs.html).
- "Home and Settings tabs are not manageable, and can't be hidden or moved" — a `PUT` naming
  either of those two tabs' ids is documented to be refused, unlike any other tab (docs:
  https://canvas.instructure.com/doc/api/tabs.html).
- The list endpoint accepts an account, course, group, or user id; the update endpoint accepts
  only a course id. There is no documented way to hide or reposition a tab for a group or a user
  context through this API — only to list one (docs:
  https://canvas.instructure.com/doc/api/tabs.html).

**Source.** https://canvas.instructure.com/doc/api/tabs.html, fetched 2026-09-10
