import { Injectable, signal } from '@angular/core';
import { Blog } from './blog.model';

@Injectable({
  providedIn: 'root'
})
export class BlogService {
  private blogs: Blog[] = [
    {
      id: '1',
      title: 'Morning',
      excerpt: 'Start your day with positivity and energy',
      content: `\n        <h2>The Beauty of Morning</h2>\n        <p>Morning is a magical time when the world awakens. The soft light of dawn paints the sky in hues of orange and pink, creating a canvas of possibilities.</p>\n        \n        <h3>Why Mornings Matter</h3>\n        <p>Starting your day with intention and purpose sets the tone for everything that follows. A peaceful morning routine can transform your entire day.</p>\n        \n        <h3>Morning Rituals</h3>\n        <ul>\n          <li>Meditation and mindfulness</li>\n          <li>Light exercise or stretching</li>\n          <li>Healthy breakfast</li>\n          <li>Journaling thoughts and goals</li>\n        </ul>\n        \n        <p>Embrace the morning. Let it be your canvas for creating a beautiful day.</p>\n      `,
      date: '2024-01-15',
      category: 'Lifestyle'
    },
    {
      id: '2',
      title: 'Afternoon',
      excerpt: 'Productivity peaks in the afternoon hours',
      content: `\n        <h2>The Power of Afternoon</h2>\n        <p>Afternoon brings a surge of energy and focus. It's the perfect time to tackle challenging tasks and make significant progress.</p>\n        \n        <h3>Maximizing Afternoon Productivity</h3>\n        <p>Our bodies and minds are primed for complex work during these hours. Strategic planning can help you make the most of this time.</p>\n        \n        <h3>Afternoon Tips</h3>\n        <ul>\n          <li>Tackle difficult projects</li>\n          <li>Take strategic breaks</li>\n          <li>Stay hydrated</li>\n          <li>Review progress and adjust plans</li>\n        </ul>\n      `,
      date: '2024-01-14',
      category: 'Productivity'
    },
    {
      id: '3',
      title: 'Evening',
      excerpt: 'Wind down and reflect on your day',
      content: `\n        <h2>The Serenity of Evening</h2>\n        <p>Evening is a time for reflection, relaxation, and preparation. As the sun sets, we can look back on our accomplishments and plan for tomorrow.</p>\n        \n        <h3>Evening Practices</h3>\n        <p>A calming evening routine helps us transition from activity to rest, ensuring better sleep and mental clarity.</p>\n        \n        <h3>Evening Rituals</h3>\n        <ul>\n          <li>Review the day's achievements</li>\n          <li>Plan tomorrow's priorities</li>\n          <li>Engage in relaxing activities</li>\n          <li>Practice gratitude</li>\n        </ul>\n        \n        <p>Let the evening be your bridge to restful sleep and renewed energy.</p>\n      `,
      date: '2024-01-13',
      category: 'Wellness'
    },
    {
      id: '4',
      title: 'Night',
      excerpt: 'The quiet hours of creativity and rest',
      content: `\n        <h2>The Magic of Night</h2>\n        <p>Night brings a unique stillness that can spark creativity and deep thinking. It's a time when the world quiets down, and our minds can wander freely.</p>\n        \n        <h3>Nighttime Benefits</h3>\n        <p>The darkness and quiet of night create an ideal environment for introspection, creative work, and restorative rest.</p>\n        \n        <h3>Nighttime Activities</h3>\n        <ul>\n          <li>Creative writing or art</li>\n          <li>Deep reading</li>\n          <li>Quality sleep</li>\n          <li>Dream journaling</li>\n        </ul>\n      `,
      date: '2024-01-12',
      category: 'Creativity'
    }
  ];

  getBlogs(): Blog[] {
    return this.blogs;
  }

  getBlogById(id: string): Blog | undefined {
    return this.blogs.find(blog => blog.id === id);
  }

  deleteBlog(id: string): void {
    const index = this.blogs.findIndex(blog => blog.id === id);
    if (index !== -1) {
      this.blogs.splice(index, 1);
    }
  }

  getFirstBlog(): Blog | undefined {
    return this.blogs.length > 0 ? this.blogs[0] : undefined;
  }
}